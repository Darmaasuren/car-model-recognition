"""Compare recognized vehicle attributes with external registration data."""
from uuid import uuid4
from time import perf_counter
from app.core.observability import event, operation, record_id
import cv2

from app.core.config import settings
from app.services.comparison.source import (
    ServiceComparisonError, download_frame, fetch_record, fetch_records, image_url_for,
)
from app.services.comparison.store import RecognitionStore


COLOR_ALIASES = {
    "цагаан": "white", "сувдан цагаан": "white", "хар": "black", "хар саарал": "black", "хөх": "blue",
    "цэнхэр": "blue", "цайвар цэнхэр": "blue", "бор": "brown", "саарал": "gray",
    "улаан": "red", "мөнгөлөг саарал": "gray", "мөнгөлөг": "gray",
}


def normalize(value):
    return " ".join(str(value or "").casefold().split())


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


@operation("recognition")
def compare_record(record, frame, recognition):
    started = perf_counter()
    results = recognition.process_image(frame)
    prediction = max(
        results,
        key=lambda result: result.model.confidence if result.model else -1.0,
        default=None,
    )
    event("recognition.completed", detected=len(results),
          model=prediction.model.label if prediction and prediction.model else None,
          model_confidence=prediction.model.confidence if prediction and prediction.model else None,
          color=prediction.color.label if prediction and prediction.color else None,
          color_confidence=prediction.color.confidence if prediction and prediction.color else None,
          duration_ms=round((perf_counter() - started) * 1000))
    source_model = normalize(f"{record.get('mark') or ''} {record.get('model') or ''}")
    source_color = normalize(record.get("color"))
    source_type = str(record.get("typeNameEng") or "")
    expected_color = COLOR_ALIASES.get(source_color, source_color)
    labels = recognition.label_groups
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
        "prediction": prediction.model_dump(mode="json", by_alias=True) if prediction else None,
    }


def compare_one(record, recognition):
    token = record_id.set(str(record.get("_id") or ""))
    try:
        return _compare_one(record, recognition)
    finally:
        record_id.reset(token)


@operation("record.process")
def _compare_one(record, recognition):
    url = image_url_for(record)
    frame = download_frame(url)
    result = compare_record(record, frame, recognition)
    result["modelVersion"] = recognition.model_version
    success, encoded = cv2.imencode(".jpg", frame)
    if not success:
        raise ServiceComparisonError("Зургийг харуулахад алдаа гарлаа.")
    filename = f"service_{uuid4().hex}.jpg"
    settings.full_photo_dir.mkdir(parents=True, exist_ok=True)
    (settings.full_photo_dir / filename).write_bytes(encoded.tobytes())
    result["imageUrl"] = f"/media/full_photo/{filename}"
    result["imageHeight"], result["imageWidth"] = frame.shape[:2]
    return result


def compare_next(recognition, token_provider=None, db_sessions=None):
    result = _compare_records([fetch_record(token_provider)], recognition, db_sessions)
    item = result["items"][0]
    if "error" in item:
        raise ServiceComparisonError(item["error"])
    return item


def compare_batch(recognition, token_provider=None, db_sessions=None):
    records = fetch_records(20, token_provider)
    return _compare_records(records, recognition, db_sessions)


def _compare_records(records, recognition, db_sessions):
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
            result = compare_one(raw, recognition)
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
