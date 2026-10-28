import base64
import binascii
from io import BytesIO

import cv2
import numpy as np
from PIL import Image
from fastapi import HTTPException

from recognition_service.config import settings


def decode_image_bytes(data: bytes):
    if not data:
        raise ValueError("Хоосон зураг байна.")
    if len(data) > settings.max_image_bytes:
        raise HTTPException(413, "Зургийн хэмжээ хэтэрсэн.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > settings.max_image_pixels:
                raise HTTPException(413, "Зургийн нягтаршил хэт өндөр байна.")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("Зураг уншигдахгүй байна.") from error
    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Зураг уншигдахгүй байна.")
    return frame


def decode_base64_image(value: str):
    value = value.strip()
    if value.lower().startswith("data:"):
        header, value = value.split(",", 1)
        if header.lower() not in {"data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"}:
            raise ValueError("Дэмжигдээгүй зургийн төрөл.")
    if len(value) > ((settings.max_image_bytes + 2) // 3) * 4:
        raise HTTPException(413, "Зургийн хэмжээ хэтэрсэн.")
    try:
        return decode_image_bytes(base64.b64decode(value, validate=True))
    except binascii.Error as error:
        raise ValueError("Base64 буруу байна.") from error


def attach_crops(frame, results):
    for result in results:
        box = result.vehicle_bbox
        crop = frame[box.y1:box.y2, box.x1:box.x2]
        ok, encoded = cv2.imencode(".png", crop)
        if not ok:
            raise ValueError("Crop encode failed")
        result.crop_base64 = base64.b64encode(encoded.tobytes()).decode("ascii")
    return results
