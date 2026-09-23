"""Durable cursor and scheduling state for the singleton HTTP poller."""
from datetime import datetime
from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ServiceSync(Base):
    __tablename__ = "service_sync_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_offset: Mapped[int] = mapped_column(Integer, default=0)
    next_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="starting")
    last_error: Mapped[str | None] = mapped_column(Text)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    config_key: Mapped[str | None] = mapped_column(Text)
