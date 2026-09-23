"""Fetch source records and compare their full photos with the classifier."""

import json
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import cv2
import numpy as np
import requests

from app.core.config import settings
from app.services.service_auth import ServiceAuthError
from app.services.seatbelt_client import check_seatbelt
from app.services.recognition_store import RecognitionStore


COLOR_ALIASES = {
    "цагаан": "white", "сувдан цагаан": "white", "хар": "black", "хар саарал": "black", "хөх": "blue",
    "цэнхэр": "blue", "цайвар цэнхэр": "blue", "бор": "brown", "саарал": "gray",
    "улаан": "red", "мөнгөлөг саарал": "gray", "мөнгөлөг": "gray",
}


class ServiceComparisonError(Exception):
    def __init__(self, message, *, retry_after=0, blocked=False):
        super().__init__(message)
        self.retry_after = retry_after
        self.blocked = blocked


def retry_after_seconds(value):
    try:
        return max(0, int(value))
    except (ValueError, TypeError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def fetch_records(limit=20, token_provider=None, overrides=None, refresh_on_401=True, omit_date_filters=False):
    url = os.getenv("SERVICE_URL", "").strip()
    token = os.getenv("SERVICE_TOKEN", "").strip().removeprefix("Bearer ").strip()
    method = os.getenv("SERVICE_METHOD", "POST").strip().upper()
    if not url or (token_provider is None and not token) or method not in {"GET", "POST"}:
        raise ServiceComparisonError("SERVICE_URL, SERVICE_TOKEN эсвэл SERVICE_METHOD тохиргоо дутуу байна.")
    try:
        params = json.loads(os.getenv("SERVICE_PARAMS_JSON", "{}"))
        body = json.loads(os.getenv("SERVICE_BODY_JSON", "{}"))
    except ValueError as error:
        raise ServiceComparisonError("SERVICE_PARAMS_JSON эсвэл SERVICE_BODY_JSON JSON формат буруу байна.") from error
    if not isinstance(params, dict) or not isinstance(body, dict):
        raise ServiceComparisonError("Service request JSON объект байх ёстой.", blocked=True)
    if omit_date_filters:
        date_fields = {"startDate", "endDate", os.getenv("SERVICE_DATE_START_FIELD", "startDate"),
                       os.getenv("SERVICE_DATE_END_FIELD", "endDate")}
        for field in date_fields:
            params.pop(field, None)
            body.pop(field, None)
    if overrides is not None:
        (body if method == "POST" else params).update(overrides)
    try:
        if token_provider is not None:
            token = token_provider.get_token()
        with requests.Session() as client:
            for attempt in range(2):
                response = client.request(
                    method, url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    params=params,
                    json=body if method == "POST" else None,
                    timeout=(10, 30),
                    allow_redirects=False,
                )
                with response:
                    if response.status_code == 401 and token_provider is not None and attempt == 0 and refresh_on_401:
                        token = token_provider.get_token(rejected_token=token)
                        continue
                    if response.status_code == 401 and token_provider is not None and not refresh_on_401:
                        # Refresh credentials now; retry the list only on the next scheduled cycle.
                        token_provider.get_token(rejected_token=token)
                        raise ServiceComparisonError("Service token шинэчилсэн; дараагийн мөчлөгт дахин оролдоно.", retry_after=300)
                    if response.status_code in {401, 403, 429, 503}:
                        raise ServiceComparisonError(
                            f"Service HTTP {response.status_code} алдаа буцаалаа.",
                            retry_after=retry_after_seconds(response.headers.get("Retry-After")),
                            blocked=response.status_code in {401, 403},
                        )
                    response.raise_for_status()
                    if response.is_redirect:
                        raise ServiceComparisonError("Service хаяг өөр хаяг руу чиглүүлж байна.")
                    payload = response.json()
                    break
    except ServiceAuthError as error:
        raise ServiceComparisonError(str(error)) from None
    except requests.HTTPError as error:
        code = error.response.status_code if error.response is not None else "unknown"
        raise ServiceComparisonError(f"Service HTTP {code} алдаа буцаалаа.") from error
    except (requests.RequestException, ValueError) as error:
        raise ServiceComparisonError("Service-ээс record авч чадсангүй.") from error
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ServiceComparisonError("Service-ийн items жагсаалт буруу байна.")
    if overrides is not None and len(items) > limit:
        raise ServiceComparisonError("Service limit-ээс олон бичлэг буцаалаа.", blocked=True)
    return items[:limit]


def fetch_record(token_provider=None):
    records = fetch_records(1, token_provider)
    if not records or not isinstance(records[0], dict):
        raise ServiceComparisonError("Service-ийн эхний record байхгүй эсвэл буруу байна.")
    return records[0]


def image_url_for(record):
    base = os.getenv("IMAGE_BASE_URL", "").strip().rstrip("/") + "/"
    path = record.get("full_photo")
    if not base.startswith("https://") or not isinstance(path, str) or not path:
        raise ServiceComparisonError("IMAGE_BASE_URL эсвэл full_photo байхгүй байна.")
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or path.startswith("/") or ".." in path.split("/"):
        raise ServiceComparisonError("full_photo зам буруу байна.")
    return urljoin(base, path)


def download_frame(url):
    try:
        # The service token is never sent to the image host.
        with requests.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as response:
            if response.status_code in {403, 429, 503}:
                raise ServiceComparisonError(
                    f"Зураг татах HTTP {response.status_code} алдаа.",
                    blocked=response.status_code == 403,
                    retry_after=max(300, retry_after_seconds(response.headers.get("Retry-After"))),
                )
            response.raise_for_status()
            if response.is_redirect:
                raise ServiceComparisonError("Зургийн хаяг өөр сервер рүү чиглүүлж байна.")
            if response.headers.get("Content-Type", "").split(";")[0].lower() not in {
                "image/jpeg", "image/png", "image/webp",
            }:
                raise ServiceComparisonError("Зургийн төрөл дэмжигдэхгүй байна.")
            chunks = bytearray()
            for chunk in response.iter_content(64 * 1024):
                chunks.extend(chunk)
                if len(chunks) > settings.max_image_bytes:
                    raise ServiceComparisonError("Зураг 15 MB-аас их байна.")
    except requests.RequestException as error:
        raise ServiceComparisonError("Зураг татаж чадсангүй.") from error
    frame = cv2.imdecode(np.frombuffer(chunks, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape[0] * frame.shape[1] > settings.max_image_pixels:
        raise ServiceComparisonError("Зураг уншигдахгүй эсвэл хэт том байна.")
    return frame


def compare_label(expected, prediction, supported):
    if not expected:
        return "MISSING_REFERENCE"
    if normalize(expected) not in {normalize(label) for label in supported}:
        return "UNSUPPORTED_CLASS"
    if prediction is None:
        return "NO_PREDICTION"
    if prediction.confidence < 0.9:
        return "LOW_CONFIDENCE"
    return "MATCH" if normalize(expected) == normalize(prediction.label) else "MISMATCH"


def compare_record(record, frame, pipeline):
    results = pipeline.process_image(frame)
    prediction = max(
        results,
        key=lambda result: result.model.confidence if result.model else -1.0,
        default=None,
    )
    source_model = normalize(f"{record.get('mark') or ''} {record.get('model') or ''}")
    source_color = normalize(record.get("color"))
    source_type = str(record.get("typeNameEng") or "")
    expected_color = COLOR_ALIASES.get(source_color, source_color)
    labels = pipeline.classifier.label_groups
    model_status = compare_label(source_model, prediction.model if prediction else None, labels["model"])
    color_status = compare_label(expected_color, prediction.color if prediction else None, labels["color"])
    # Registration type names can differ from the model's car/truck/van labels.
    type_status = (
        compare_label(source_type, prediction.vehicle_type if prediction else None, labels["type"])
        if normalize(source_type) in {normalize(label) for label in labels["type"]}
        else "UNMAPPED_REFERENCE" if source_type else "MISSING_REFERENCE"
    )
    view_status = "MISSING_REFERENCE"
    if not results:
        image_status = "NO_VEHICLE_DETECTED"
        if model_status not in {"MISSING_REFERENCE", "UNSUPPORTED_CLASS"}:
            model_status = image_status
        if color_status not in {"MISSING_REFERENCE", "UNSUPPORTED_CLASS"}:
            color_status = image_status
        if type_status not in {"MISSING_REFERENCE", "UNMAPPED_REFERENCE"}:
            type_status = image_status
    else:
        image_status = "OK"
    return {
        "recordId": str(record.get("_id") or ""),
        "plate": str(record.get("plate") or ""),
        "eventDate": str(record.get("event_date") or ""),
        "sourceMark": str(record.get("mark") or ""),
        "sourceModel": str(record.get("model") or ""),
        "sourceColor": str(record.get("color") or ""),
        "sourceType": source_type,
        "imageStatus": image_status,
        "modelStatus": model_status,
        "colorStatus": color_status,
        "typeStatus": type_status,
        "viewStatus": view_status,
        "seatbelt": check_seatbelt(frame, prediction),
        "prediction": prediction.model_dump(mode="json", by_alias=True) if prediction else None,
    }


def compare_one(record, pipeline):
    url = image_url_for(record)
    frame = download_frame(url)
    result = compare_record(record, frame, pipeline)
    success, encoded = cv2.imencode(".jpg", frame)
    if not success:
        raise ServiceComparisonError("Зургийг харуулахад алдаа гарлаа.")
    filename = f"service_{uuid4().hex}.jpg"
    (settings.crop_dir / filename).write_bytes(encoded.tobytes())
    result["imageUrl"] = f"/media/crops/{filename}"
    result["imageHeight"], result["imageWidth"] = frame.shape[:2]
    return result


def compare_next(pipeline, token_provider=None, db_sessions=None):
    result = _compare_records([fetch_record(token_provider)], pipeline, db_sessions)
    item = result["items"][0]
    if "error" in item:
        raise ServiceComparisonError(item["error"])
    return item


def compare_batch(pipeline, token_provider=None, db_sessions=None):
    records = fetch_records(20, token_provider)
    return _compare_records(records, pipeline, db_sessions)


def _compare_records(records, pipeline, db_sessions):
    store = RecognitionStore(db_sessions) if db_sessions is not None else None
    invalid = {}
    if store:
        # Persist the entire batch before downloading any image.
        for index, raw in enumerate(records):
            if isinstance(raw, dict):
                try:
                    store.enqueue(raw)
                except (ValueError, TypeError):
                    invalid[index] = "Service-ийн _id эсвэл event_date буруу байна."
    results = []
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            results.append({"recordId": "", "plate": "", "error": "Record формат буруу байна."})
            continue
        started = False
        try:
            if index in invalid:
                raise ServiceComparisonError(invalid[index])
            if store:
                started = store.start(raw)
                if not started:
                    raise ServiceComparisonError("Энэ бичлэгийг өөр хүсэлт боловсруулж байна.")
            result = compare_one(raw, pipeline)
        except (ServiceComparisonError, OSError, ValueError, RuntimeError, cv2.error) as error:
            message = str(error) if isinstance(error, ServiceComparisonError) else "Зургийг боловсруулахад алдаа гарлаа."
            if store and started:
                store.fail(str(raw["_id"]).strip(), message)
            results.append({
                "recordId": str(raw.get("_id") or ""),
                "plate": str(raw.get("plate") or ""),
                "error": message,
            })
        else:
            if store:
                store.complete(str(raw["_id"]).strip(), result)
            results.append(result)
    return {"items": results, "count": len(results)}
