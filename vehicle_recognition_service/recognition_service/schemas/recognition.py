from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from recognition_service.schemas.common import ApiModel


class Prediction(ApiModel):
    label: str
    confidence: float = Field(ge=0.0, le=1.0)


class VehicleRecognitionResult(ApiModel):
    model: Prediction | None = None
    color: Prediction | None = None
    vehicle_type: Prediction | None = None
    view: Prediction | None = None


class BoundingBox(ApiModel):
    x1: int
    y1: int
    x2: int
    y2: int

    @model_validator(mode="after")
    def validate_coordinates(self):
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Bounding box coordinate буруу байна.")
        return self




class VehicleBboxRequest(ApiModel):
    event_id: str | None = None
    image_base64: str = Field(min_length=1)
    vehicle_bbox: BoundingBox


class VehicleBboxResponse(ApiModel):
    event_id: str
    vehicle_bbox: BoundingBox
    result: VehicleRecognitionResult | None = None
    reason_code: Literal["CLASSIFICATION_FAILED"] | None = None


class PlateVehicleRequest(ApiModel):
    event_id: str | None = None
    image_base64: str = Field(min_length=1)
    plate_bbox: BoundingBox = Field(alias="plateBbox")


class PlateVehicleResponse(ApiModel):
    event_id: str
    matched: bool
    plate_bbox: BoundingBox
    vehicle_bbox: BoundingBox | None = None
    match_score: float | None = None
    result: VehicleRecognitionResult | None = None
    reason_code: Literal[
        "NO_VEHICLE_DETECTED",
        "NO_MATCHING_VEHICLE",
        "CLASSIFICATION_FAILED",
    ] | None = None
    reason: str | None = None




class RecognitionResult(VehicleRecognitionResult):
    event_id: str
    detected_at: datetime
    track_id: int | None = None
    crop_url: str | None = None
    vehicle_bbox: BoundingBox | None = None
    crop_base64: str | None = None


class InferenceResponse(ApiModel):
    results: list[RecognitionResult]
    model_version: str
    label_groups: dict[str, list[str]]
