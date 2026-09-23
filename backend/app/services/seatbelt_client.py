"""Seatbelt enrichment for service comparisons; images remain in memory."""
import math
import os
from threading import Lock
from time import sleep
from urllib.parse import urlsplit

import cv2
from pydantic import BaseModel, Field, ValidationError
import requests

_lock = Lock()
LABELS = {"person-seatbelt", "person-noseatbelt", "seatbelt", "windshield"}


class Detection(BaseModel):
    class_id: int
    class_name: str
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[float, float, float, float]


class ImageSize(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SeatbeltResponse(BaseModel):
    image: ImageSize
    detections: list[Detection]
    count: int = Field(ge=0)


def outcome(status, reason, **kwargs):
    return {"status": status, "reason": reason, "detections": [], **kwargs}


def check_seatbelt(frame, prediction):
    if prediction is None:
        return outcome("skipped", "Машин нэг утгатай тодорхойлогдоогүй.")
    view = getattr(prediction, "view", None)
    if view is None:
        return outcome("skipped", "Харагдац тодорхойгүй.")
    if view.label != "front_side":
        return outcome("skipped", "Урд талаас харагдаагүй.")
    try:
        threshold = float(os.getenv("SEATBELT_VIEW_MIN_CONFIDENCE", "0.90"))
        if not 0 <= threshold <= 1:
            raise ValueError()
    except ValueError:
        return outcome("error", "Seatbelt харагдацын босго буруу байна.")
    if view.confidence < threshold:
        return outcome("skipped", "Харагдацын итгэлцэл бага.")
    url = os.getenv("SEATBELT_URL", "").strip()
    if not url:
        return outcome("skipped", "Seatbelt service тохируулаагүй.")
    if urlsplit(url).scheme not in {"http", "https"} or not urlsplit(url).hostname:
        return outcome("error", "Seatbelt service-ийн URL буруу байна.")
    bbox = getattr(prediction, "vehicle_bbox", None)
    if bbox is None:
        return outcome("error", "Машины тайралтын координат байхгүй.")
    height, width = frame.shape[:2]
    if not (0 <= bbox.x1 < bbox.x2 <= width and 0 <= bbox.y1 < bbox.y2 <= height):
        return outcome("error", "Машины тайралтын координат буруу байна.")
    crop = frame[bbox.y1:bbox.y2, bbox.x1:bbox.x2]
    try:
        success, encoded = cv2.imencode(".png", crop)
        if not success:
            return outcome("error", "Seatbelt зураг бэлтгэж чадсангүй.")
        data = encoded.tobytes()
        if len(data) > 10 * 1024 * 1024 or crop.shape[0] * crop.shape[1] > 20_000_000:
            return outcome("error", "Seatbelt зураг хэмжээний хязгаараас их байна.")
        with _lock:
            for attempt in range(2):
                with requests.post(url, data=data, headers={"Content-Type": "image/png"},
                                   timeout=(3, 30), allow_redirects=False) as response:
                    if response.status_code == 503 and attempt == 0:
                        sleep(1)
                        continue
                    if response.status_code == 503:
                        return outcome("error", "Seatbelt service завгүй байна.")
                    if response.status_code != 200:
                        return outcome("error", "Seatbelt service шалгалтыг гүйцэтгэж чадсангүй.")
                    result = SeatbeltResponse.model_validate(response.json())
                    break
        if (result.count != len(result.detections)
                or result.image.width != crop.shape[1] or result.image.height != crop.shape[0]):
            raise ValueError()
        for item in result.detections:
            x1, y1, x2, y2 = item.bbox
            if (item.class_name not in LABELS or not all(math.isfinite(v) for v in item.bbox)
                    or not (0 <= x1 < x2 <= result.image.width and 0 <= y1 < y2 <= result.image.height)):
                raise ValueError()
        people = [d for d in result.detections if d.class_name.startswith("person-")]
        return outcome(
            "completed" if people else "unknown",
            "Хүний бүсний төлөв илэрсэн." if people else "Бүс зүүсэн эсэхийг тодорхойлох боломжгүй.",
            detections=[{"className": d.class_name, "confidence": d.confidence,
                         "bbox": list(d.bbox)} for d in result.detections],
            image=result.image.model_dump(),
        )
    except requests.Timeout:
        return outcome("error", "Seatbelt service-ийн хариу хүлээх хугацаа дууссан.")
    except requests.RequestException:
        return outcome("error", "Seatbelt service-тэй холбогдож чадсангүй.")
    except (ValidationError, ValueError, cv2.error):
        return outcome("error", "Seatbelt зураг эсвэл response-ийн бүтэц буруу байна.")


def enrich_results(frame, results):
    """Enrich each recognized vehicle using its own crop, including video events."""
    from app.schemas.recognition import SeatbeltResult

    for result in results:
        result.seatbelt = SeatbeltResult.model_validate(check_seatbelt(frame, result))
    return results


def recognize_file_image(pipeline, frame):
    return enrich_results(frame, pipeline.process_image(frame))
