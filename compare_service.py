# compare_service.py
import csv
import json
import os
from getpass import getpass
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests


SERVICE_URL = "https://traffic-police.odt.mn/api/record/table"
SERVICE_METHOD = os.getenv("SERVICE_METHOD", "POST").strip().upper()
# GET нь эхний тохиргоо. Service POST ашигладаг бол дээрх GET-ийг солино.

# Жишээ: {"Authorization": "Bearer ..."} эсвэл {"API-Key": "..."}
# Нууц утгыг source code-д бичихгүй.
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "").strip()

SERVICE_HEADERS = {
    "Accept": "application/json",
}

# Service-ийн бодит query/body-г environment-оор тохируулна.
SERVICE_PARAMS = json.loads(os.getenv("SERVICE_PARAMS_JSON", "{}"))
SERVICE_BODY = json.loads(os.getenv("SERVICE_BODY_JSON", "{}"))

# full_photo-ийн relative path-ийг бүтэн URL болгох үндсэн хаяг.
# Зургийн сервер өөр бол энэ үндсэн URL-ийг солино.
IMAGE_BASE_URL = os.getenv(
    "IMAGE_BASE_URL", "https://traffic-police.odt.mn/main/"
).rstrip("/") + "/"

BACKEND_URL = os.getenv(
    "BACKEND_URL", "http://localhost:8008/api/v1"
).rstrip("/")

THRESHOLD = 0.90
LIMIT = 10
MAX_IMAGE_BYTES = 15_728_640

# Ажиллаж буй checkpoint өөрчлөгдвөл жагсаалтыг шинэчилнэ.
SUPPORTED_MODELS = [
    "Hyundai Porter",
    "Hyundai Sonata",
    "KIA Bongo3",
    "Lexus HS250h",
    "Lexus RX",
    "Nissan X-Trail",
    "Toyota Harrier",
    "Toyota Alphard",
    "Toyota Aqua",
    "Toyota Camry",
    "Toyota Crown",
    "Toyota Land Cruiser",
    "Toyota Land Cruiser Prado",
    "Toyota Prius",
    "Toyota Prius Alpha",
    "Toyota Sai",
]

SUPPORTED_COLORS = {
    "black", "blue", "brown", "gray", "red", "white"
}

COLOR_ALIASES = {
    "цагаан": "white",
    "сувдан цагаан": "white",
    "хар": "black",
    "хөх": "blue",
    "цэнхэр": "blue",
    "бор": "brown",
    "саарал": "gray",
    "мөнгөлөг": "gray",
    "мөнгөлөг саарал": "gray",
    "улаан": "red",
}

# Зөвхөн баталгаажуулсан өөр нэршлүүдийг нэмнэ.
MODEL_ALIASES = {}

# Нэршил нь тодорхой, сургасан ангилалд байхгүй утгууд.
KNOWN_UNSUPPORTED_MODELS = {"honda fit"}
KNOWN_UNSUPPORTED_COLORS = {"мөнгөлөг", "silver"}


def normalize(value):
    return " ".join(str(value or "").casefold().split())


MODEL_LOOKUP = {
    normalize(label): label for label in SUPPORTED_MODELS
}


class RecordError(Exception):
    pass


def fetch_records(client):
    if SERVICE_METHOD not in {"GET", "POST"}:
        raise ValueError("SERVICE_METHOD нь GET эсвэл POST байна.")

    token = SERVICE_TOKEN or getpass("Service-ийн Bearer token: ").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise ValueError("Bearer token хоосон байна.")

    kwargs = {
        "headers": {**SERVICE_HEADERS, "Authorization": f"Bearer {token}"},
        "params": SERVICE_PARAMS,
        "timeout": (10, 30),
    }
    if SERVICE_METHOD == "POST":
        kwargs["json"] = SERVICE_BODY

    response = client.request(
        SERVICE_METHOD, SERVICE_URL, **kwargs
    )
    response.raise_for_status()

    records = response.json()["items"]
    if not isinstance(records, list):
        raise ValueError("Response-ийн items нь жагсаалт биш байна.")

    return records[:LIMIT]


def resolve_model(mark, model):
    model_name = normalize(model)
    if not model_name:
        return "", "MISSING_REFERENCE"

    candidates = [
        normalize(f"{mark or ''} {model}"),
        model_name,
    ]

    for candidate in candidates:
        candidate = normalize(
            MODEL_ALIASES.get(candidate, candidate)
        )
        if candidate in MODEL_LOOKUP:
            return MODEL_LOOKUP[candidate], None

    if any(c in KNOWN_UNSUPPORTED_MODELS for c in candidates):
        return candidates[0], "UNSUPPORTED_CLASS"

    # Танихгүй нэршил нь товчлол, алдаа байж болно.
    return candidates[0], "UNMAPPED_LABEL"


def resolve_color(color):
    value = normalize(color)
    if not value:
        return "", "MISSING_REFERENCE"

    if value in KNOWN_UNSUPPORTED_COLORS:
        return value, "UNSUPPORTED_CLASS"

    value = COLOR_ALIASES.get(value, value)
    if value in SUPPORTED_COLORS:
        return value, None

    return value, "UNMAPPED_LABEL"


def download_image(client, image_url):
    try:
        # Service-ийн нууц header-ийг зураг руу дамжуулахгүй.
        with client.get(
            image_url, stream=True, timeout=(10, 30)
        ) as response:
            response.raise_for_status()

            mime = response.headers.get(
                "Content-Type", ""
            ).split(";")[0].strip().lower()

            extensions = {
                "image/jpeg": "jpg",
                "image/png": "png",
                "image/webp": "webp",
            }
            if mime not in extensions:
                raise RecordError("UNSUPPORTED_IMAGE_TYPE")

            data = bytearray()
            for chunk in response.iter_content(64 * 1024):
                data.extend(chunk)
                if len(data) > MAX_IMAGE_BYTES:
                    raise RecordError("IMAGE_TOO_LARGE")

            if not data:
                raise RecordError("EMPTY_IMAGE")

            return bytes(data), mime, extensions[mime]

    except requests.RequestException as error:
        raise RecordError("IMAGE_DOWNLOAD_FAILED") from error


def recognize(client, image_url):
    data, mime, extension = download_image(client, image_url)

    try:
        response = client.post(
            f"{BACKEND_URL}/inference/image",
            files={
                "file": (f"vehicle.{extension}", data, mime)
            },
            timeout=(10, 120),
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise RecordError("INFERENCE_FAILED") from error

    try:
        results = response.json()["results"]
        if not isinstance(results, list):
            raise ValueError("Invalid results")
    except (ValueError, KeyError, TypeError) as error:
        raise RecordError("INVALID_INFERENCE_RESPONSE") from error

    if len(results) == 0:
        raise RecordError("NO_VEHICLE_DETECTED")
    if len(results) > 1:
        raise RecordError("AMBIGUOUS_VEHICLE")
    if not isinstance(results[0], dict):
        raise RecordError("INVALID_INFERENCE_RESPONSE")

    return results[0]


def compare(expected, reference_status, prediction, image_status):
    if reference_status:
        return reference_status
    if image_status != "OK":
        return image_status
    if not prediction:
        return "NO_PREDICTION"

    label = prediction.get("label")
    confidence = prediction.get("confidence")

    if (
        not isinstance(label, str)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        return "INVALID_PREDICTION"

    if confidence < THRESHOLD:
        return "LOW_CONFIDENCE"

    return (
        "MATCH"
        if normalize(label) == normalize(expected)
        else "MISMATCH"
    )


def process_record(client, raw):
    expected_model, model_reference_status = resolve_model(
        raw.get("mark"), raw.get("model")
    )
    expected_color, color_reference_status = resolve_color(
        raw.get("color")
    )

    photo_path = raw.get("full_photo")
    image_url = (
        urljoin(IMAGE_BASE_URL, photo_path)
        if photo_path
        else ""
    )

    prediction = {}
    image_status = "OK"

    if not image_url:
        image_status = "MISSING_IMAGE_URL"
    else:
        try:
            prediction = recognize(client, image_url)
        except RecordError as error:
            image_status = str(error)

    model_prediction = prediction.get("model") or {}
    color_prediction = prediction.get("color") or {}

    if not isinstance(model_prediction, dict):
        model_prediction = {}
    if not isinstance(color_prediction, dict):
        color_prediction = {}

    return {
        "record_id": raw.get("_id", ""),
        "event_date": raw.get("event_date", ""),
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "image_url": image_url,
        "image_status": image_status,
        "source_mark": raw.get("mark", ""),
        "source_model": raw.get("model", ""),
        "source_color": raw.get("color", ""),
        "expected_model": expected_model,
        "predicted_model": model_prediction.get("label", ""),
        "model_confidence": model_prediction.get("confidence", ""),
        "model_status": compare(
            expected_model,
            model_reference_status,
            model_prediction,
            image_status,
        ),
        "expected_color": expected_color,
        "predicted_color": color_prediction.get("label", ""),
        "color_confidence": color_prediction.get("confidence", ""),
        "color_status": compare(
            expected_color,
            color_reference_status,
            color_prediction,
            image_status,
        ),
    }


def main():
    # Credentials зураг/backend руу холилдохоос сэргийлж
    # service болон боловсруулалтын client-ийг салгасан.
    with requests.Session() as service_client:
        records = fetch_records(service_client)

    if not records:
        print("Бүртгэл олдсонгүй.")
        return

    filename = datetime.now(timezone.utc).strftime(
        "comparison_%Y%m%d_%H%M%S_%f.csv"
    )

    with (
        requests.Session() as client,
        open(filename, "w", newline="", encoding="utf-8-sig") as output,
    ):
        writer = None

        for raw in records:
            row = process_record(client, raw)

            if writer is None:
                writer = csv.DictWriter(output, fieldnames=list(row))
                writer.writeheader()

            writer.writerow(row)
            output.flush()

            print(
                f'{row["record_id"]}: '
                f'image={row["image_status"]}, '
                f'model={row["model_status"]}, '
                f'color={row["color_status"]}'
            )

    print(f"Тайлан хадгаллаа: {filename}")


if __name__ == "__main__":
    main()
