"""Validated wire contract of the combined windshield/seatbelt service."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.schemas.common import ApiModel


class Windshield(ApiModel):
    bbox: tuple[float, float, float, float]
    crop_bbox: tuple[int, int, int, int]
    confidence: float = Field(ge=0, le=1)


class Detection(ApiModel):
    class_id: int
    label: str
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[float, float, float, float]
    windshield_index: int = Field(ge=0)
    person_confidence: float | None = Field(default=None, ge=0, le=1)
    role_confidence: float | None = Field(default=None, ge=0, le=1)
    phone_usage: bool | None = None
    phone_confidence: float | None = Field(default=None, ge=0, le=1)
    role: Literal["driver", "passenger", "unknown"] | None = None


class ServiceResponse(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    windshields: list[Windshield]
    detections: list[Detection]

    @model_validator(mode="after")
    def check_boxes(self):
        for item in [*self.windshields, *self.detections]:
            boxes = [item.bbox]
            if isinstance(item, Windshield):
                boxes.append(item.crop_bbox)
            for x1, y1, x2, y2 in boxes:
                if not (0 <= x1 < x2 <= self.width and 0 <= y1 < y2 <= self.height):
                    raise ValueError("Invalid detection bounds")
        if any(d.windshield_index >= len(self.windshields) for d in self.detections):
            raise ValueError("Invalid windshield reference")
        return self




class BooleanPrediction(BaseModel):
    value: bool | None
    confidence: float | None = Field(ge=0, le=1)


class RolePrediction(BaseModel):
    value: Literal["driver", "passenger"] | None
    confidence: float | None = Field(ge=0, le=1)


class Occupant(BaseModel):
    person_id: int = Field(ge=0)
    bbox: tuple[float, float, float, float]
    confidence: float = Field(ge=0, le=1)
    role: RolePrediction
    seatbelt: BooleanPrediction
    phone_usage: BooleanPrediction


class OccupantWindshield(BaseModel):
    id: int = Field(ge=0)
    bbox: tuple[int, int, int, int]
    confidence: float = Field(ge=0, le=1)
    persons: list[Occupant]


class ImageSize(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class OccupantResponse(BaseModel):
    image: ImageSize
    windshield_count: int = Field(ge=0)
    person_count: int = Field(ge=0)
    windshields: list[OccupantWindshield]

    def to_service_response(self) -> ServiceResponse:
        if self.windshield_count != len(self.windshields) or self.person_count != sum(len(w.persons) for w in self.windshields):
            raise ValueError("Inconsistent detection counts")
        detections = []
        for index, windshield in enumerate(self.windshields):
            for person in windshield.persons:
                known = person.seatbelt.value is not None and person.seatbelt.confidence is not None
                label = ("person_seatbelt" if person.seatbelt.value else "person_no_seatbelt") if known else "person_unknown"
                detections.append(Detection(
                    class_id=(1 if person.seatbelt.value else 0) if known else -1,
                    label=label, confidence=person.seatbelt.confidence if known else 0,
                    bbox=person.bbox, windshield_index=index,
                    role=person.role.value, role_confidence=person.role.confidence,
                    person_confidence=person.confidence,
                    phone_usage=person.phone_usage.value, phone_confidence=person.phone_usage.confidence,
                ))
        return ServiceResponse(
            width=self.image.width, height=self.image.height,
            windshields=[Windshield(bbox=w.bbox, crop_bbox=w.bbox, confidence=w.confidence) for w in self.windshields],
            detections=detections,
        )
