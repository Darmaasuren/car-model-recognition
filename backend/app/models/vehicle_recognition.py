"""One source event and its latest comparison result."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user_model import utcnow


class VehicleRecognition(Base):
    __tablename__ = "vehicle_recognitions"
    __table_args__ = (CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_record_id: Mapped[str] = mapped_column(Text, unique=True)
    plate: Mapped[str] = mapped_column(Text, default="")
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_mark: Mapped[str] = mapped_column(Text, default="")
    source_model: Mapped[str] = mapped_column(Text, default="")
    source_color: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(Text, default="")
    source_image_path: Mapped[str] = mapped_column(Text, default="")
    local_image_path: Mapped[str | None] = mapped_column(Text)
    image_width: Mapped[int | None] = mapped_column(Integer)
    image_height: Mapped[int | None] = mapped_column(Integer)
    vehicle_bbox: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    prediction: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    comparison: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    seatbelt_result: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    model_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
