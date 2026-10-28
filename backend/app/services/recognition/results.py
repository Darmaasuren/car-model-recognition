"""Validate recognition results and materialize crops in backend storage."""
from collections import OrderedDict
from threading import Lock, local
from uuid import UUID

import math
import logging
import cv2
from app.core.observability import event
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.recognition import RecognitionResult
from app.services.recognition.client import RecognitionClient, RecognitionServiceError


class RecognitionResults:
    def __init__(self, media, client: RecognitionClient, seatbelt=None):
        self.seatbelt = seatbelt
        self.media = media
        self.client = client
        self._metadata = local()
        self.cache = OrderedDict()
        self.cache_lock = Lock()

    @property
    def label_groups(self):
        return getattr(self._metadata, "labels", {})

    @label_groups.setter
    def label_groups(self, value):
        self._metadata.labels = value

    @property
    def model_version(self):
        return getattr(self._metadata, "version", "unknown")

    @model_version.setter
    def model_version(self, value):
        self._metadata.version = value

    def process_image(self, frame):
        ok, encoded = cv2.imencode(".png", frame)
        if not ok:
            raise ValueError("Зургийг бэлтгэж чадсангүй.")
        filename, content_type = "image.png", "image/png"
        if encoded.nbytes > settings.max_image_bytes:
            # A compressed JPEG can expand beyond the upload limit when converted to PNG.
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ok:
                raise ValueError("Зургийг бэлтгэж чадсангүй.")
            filename, content_type = "image.jpg", "image/jpeg"
        data = self.client.recognize_image(filename, encoded.tobytes(), content_type)
        try:
            results = [RecognitionResult.model_validate(raw) for raw in data["results"]]
            self.label_groups, self.model_version = data["labelGroups"], data["modelVersion"]
            height, width = frame.shape[:2]
            for result in results:
                bbox = result.vehicle_bbox
                if bbox is None or not (0 <= bbox.x1 < bbox.x2 <= width and 0 <= bbox.y1 < bbox.y2 <= height):
                    raise ValueError("Invalid remote bbox")
                UUID(result.event_id)
                crop = frame[bbox.y1:bbox.y2, bbox.x1:bbox.x2]
                result.crop_url = self.media.save_crop(crop, result.event_id)
                if self.seatbelt is not None:
                    result.seatbelt = self.seatbelt.analyze(crop, result.view, bbox)
                    self.save_windshield_crops(crop, result)
                    self.save_person_crops(crop, result)
            return results
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise RecognitionServiceError("Recognition service-ийн хариу буруу байна.", 502) from error

    def save_windshield_crops(self, vehicle_crop, result):
        """Persist validated windshield regions without losing recognition on disk errors."""
        height, width = vehicle_crop.shape[:2]
        for index, windshield in enumerate((result.seatbelt or {}).get("windshields", [])):
            windshield["cropUrl"] = None
            try:
                x1, y1, x2, y2 = windshield["cropBbox"]
                if (not all(isinstance(v, int) for v in (x1, y1, x2, y2))
                        or not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height)):
                    raise ValueError("Invalid windshield crop bounds")
                crop = vehicle_crop[y1:y2, x1:x2]
                windshield["cropUrl"] = self.media.save_windshield_crop(
                    crop, result.event_id, index)
                event("windshield.crop.saved", event_id=result.event_id,
                      windshield_index=index, crop_url=windshield["cropUrl"],
                      width=x2 - x1, height=y2 - y1)
            except (OSError, RuntimeError, ValueError, TypeError, KeyError, cv2.error) as error:
                windshield["cropError"] = "CROP_SAVE_FAILED"
                event("windshield.crop.failed", logging.ERROR, event_id=result.event_id,
                      windshield_index=index, error_type=type(error).__name__)

    def save_person_crops(self, vehicle_crop, result):
        """Save each person's original-resolution crop beside their predictions."""
        height, width = vehicle_crop.shape[:2]
        for index, person in enumerate((result.seatbelt or {}).get("detections", [])):
            person["cropUrl"] = None
            try:
                left, top, right, bottom = person["bbox"]
                if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                    raise ValueError("Invalid person crop bounds")
                # Match the classification service's outward rounding.
                x1, y1 = math.floor(left), math.floor(top)
                x2, y2 = math.ceil(right), math.ceil(bottom)
                person["cropUrl"] = self.media.save_person_crop(
                    vehicle_crop[y1:y2, x1:x2], result.event_id, index)
            except (OSError, RuntimeError, ValueError, TypeError, KeyError, cv2.error) as error:
                person["cropError"] = "CROP_SAVE_FAILED"
                event("person.crop.failed", logging.ERROR, event_id=result.event_id,
                      person_index=index, error_type=type(error).__name__)

    def tracking_events(self, path, sequence):
        data = self.client.tracking_events(path, sequence)
        events = []
        for event in data["events"]:
            raw = event["result"]
            key = raw["eventId"]
            # Avoid decoding and saving the same crop for repeated viewer polls.
            with self.cache_lock:
                result = self.cache.get(key)
                if result is None:
                    try:
                        UUID(key)
                        result = RecognitionResult.model_validate(raw)
                        crop = self.media.decode_base64_image(raw["cropBase64"], settings.max_image_pixels * 4, settings.max_image_pixels)
                        result.crop_url = self.media.save_crop(crop, key)
                        self.cache[key] = result
                        while len(self.cache) > 1000:
                            self.cache.popitem(last=False)
                    except (KeyError, TypeError, ValueError) as error:
                        raise RecognitionServiceError("Recognition event буруу байна.", 502) from error
                events.append((event["sequence"], result))
        return events, data["status"], data.get("error")
