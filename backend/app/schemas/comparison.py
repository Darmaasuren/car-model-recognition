"""Comparison API responses; unset optional fields preserve existing JSON payloads."""
from datetime import datetime
from typing import Any
from pydantic import field_serializer

from app.schemas.common import ApiModel


class ComparisonResult(ApiModel):
    record_id: str
    plate: str = ""
    event_date: str = ""
    source_mark: str = ""
    source_model: str = ""
    source_color: str = ""
    source_type: str = ""
    status: str | None = None
    image_url: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    image_status: str | None = None
    model_status: str | None = None
    color_status: str | None = None
    type_status: str | None = None
    view_status: str | None = None
    model_version: str | None = None
    prediction: dict[str, Any] | None = None
    error: str | None = None


class ComparisonBatch(ApiModel):
    items: list[ComparisonResult]
    count: int


class ComparisonHistory(ComparisonBatch):
    total: int
    offset: int
    limit: int


class WorkerStatus(ApiModel):
    status: str
    counts: dict[str, int]
    error: str | None = None
    next_request_at: datetime | None = None
    last_success_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    offset: int | None = None

    @field_serializer("next_request_at", "last_success_at", "window_start", "window_end", when_used="json")
    def serialize_timestamp(self, value):
        return value.isoformat() if value is not None else None
