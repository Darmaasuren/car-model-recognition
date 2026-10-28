"""Image encoding, HTTP transport and validation for seatbelt inference."""
import cv2
import requests
from app.core.config import SeatbeltSettings
from app.schemas.seatbelt import OccupantResponse


class SeatbeltClient:
    def __init__(self, config: SeatbeltSettings):
        self.config = config

    def predict(self, crop):
        height, width = crop.shape[:2]
        ok, encoded = cv2.imencode(".png", crop)
        if not ok:
            raise ValueError("Encoding failed")
        content_type, filename = "image/png", "vehicle.png"
        if encoded.nbytes > 10 * 1024 * 1024:
            ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
            content_type, filename = "image/jpeg", "vehicle.jpg"
            if not ok or encoded.nbytes > 10 * 1024 * 1024:
                raise ValueError("Crop exceeds service limit")
        with requests.post(self.config.url + "/detect", files={"file": (filename, encoded.tobytes(), content_type)},
                           headers={"API-Key": self.config.api_key},
                           timeout=(5, self.config.timeout), allow_redirects=False) as response:
            if response.status_code != 200:
                raise requests.RequestException("Service response failed")
            data = OccupantResponse.model_validate(response.json()).to_service_response()
        if (data.width, data.height) != (width, height):
            raise ValueError("Response dimensions differ from crop")
        return data
