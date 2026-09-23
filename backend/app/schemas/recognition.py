from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import ApiModel


class Prediction(ApiModel):
    label: str
    confidence: float = Field(ge=0.0, le=1.0)


class PlateRecognitionResult(ApiModel):
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


class SeatbeltDetection(ApiModel):
    class_name: str
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[float, float, float, float]


class SeatbeltImage(ApiModel):
    width: int
    height: int


class SeatbeltResult(ApiModel):
    status: Literal["completed", "unknown", "skipped", "error"]
    reason: str
    detections: list[SeatbeltDetection] = Field(default_factory=list)
    image: SeatbeltImage | None = None


class RecognitionResult(PlateRecognitionResult):
    event_id: str
    detected_at: datetime
    track_id: int | None = None
    crop_url: str | None = None
    vehicle_bbox: BoundingBox | None = None
    seatbelt: SeatbeltResult | None = None


class InferenceResponse(ApiModel):
    results: list[RecognitionResult]


class RecognitionEvent(ApiModel):
    type: Literal["recognition"] = "recognition"
    camera_id: str
    result: RecognitionResult


class VideoSessionResponse(ApiModel):
    session_id: str


class VideoRecognitionEvent(ApiModel):
    type: Literal["recognition"] = "recognition"
    session_id: str
    result: RecognitionResult


class VideoStatusEvent(ApiModel):
    type: Literal["status"] = "status"
    session_id: str
    status: Literal[
        "pending",
        "running",
        "completed",
        "error",
        "stopped",
    ]
    error: str | None = None


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
    result: PlateRecognitionResult | None = None
    reason_code: Literal[
        "NO_VEHICLE_DETECTED",
        "NO_MATCHING_VEHICLE",
        "CLASSIFICATION_FAILED",
    ] | None = None
    reason: str | None = None
