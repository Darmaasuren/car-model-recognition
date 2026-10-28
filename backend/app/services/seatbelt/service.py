"""Front-view gating and failure-isolated seatbelt result enrichment."""
from datetime import datetime, timezone
import cv2
import requests
from app.core.config import get_seatbelt_settings
from app.services.seatbelt.client import SeatbeltClient


class SeatbeltService:
    def __init__(self, config=None, client=None):
        self.config = config if config is not None else get_seatbelt_settings()
        self.client = client if client is not None else SeatbeltClient(self.config)

    def analyze(self, crop, view, bbox):
        height, width = crop.shape[:2]
        result = {
            "schemaVersion": 1, "status": "DISABLED",
            "processedAt": datetime.now(timezone.utc).isoformat(),
            "view": view.model_dump() if view else None,
            "thresholds": {"frontView": self.config.front_conf},
            "modelVersions": {"windshield": self.config.windshield_model_version,
                              "seatbelt": self.config.seatbelt_model_version},
            "image": {"coordinateSpace": "vehicle_crop", "bboxFormat": "xyxy", "units": "pixels",
                      "width": width, "height": height, "vehicleBboxInOriginal": bbox.model_dump()},
            "windshields": [], "detections": [], "error": None,
        }
        if not self.config.enabled:
            return result
        if view is None or view.confidence < self.config.front_conf:
            result["status"] = "SKIPPED_UNCERTAIN_VIEW"
            return result
        if view.label != "front_side":
            result["status"] = "SKIPPED_NOT_FRONT"
            return result
        try:
            data = self.client.predict(crop)
            result.update(data.model_dump(by_alias=True, exclude={"width", "height"}))
            result["status"] = ("NO_WINDSHIELD" if not data.windshields else
                                "COMPLETED" if data.detections
                                else "NO_OCCUPANT_DETECTED")
        except (requests.RequestException, ValueError, cv2.error) as error:
            result["status"] = "ERROR"
            result["error"] = {"code": "SERVICE_TIMEOUT" if isinstance(error, requests.Timeout) else "SERVICE_ERROR",
                               "message": "Seatbelt шалгалтыг гүйцэтгэж чадсангүй."}
        return result
