"""Fetch the first 20 records without date filters, at most every 20 minutes."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
from time import perf_counter
from app.core.observability import event, operation
from app.core.config import get_comparison_settings
from threading import Event

from sqlalchemy import select, update, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.sync_state import ServiceSync
from app.models.recognition import VehicleRecognition as Row
from app.services.comparison.store import RecognitionStore
from app.services.comparison.compare import compare_one
from app.services.comparison.source import ServiceComparisonError, fetch_records

INTERVAL = 1200
IMAGE_RETRY_INTERVAL = 1800
PAGE_SIZE = 20
MAX_ATTEMPTS = 3


def now_utc():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


@dataclass(frozen=True)
class PollConfig:
    fingerprint: str

    @classmethod
    def from_env(cls):
        config = get_comparison_settings()
        key = sha256(json.dumps([
            config.url, config.method,
            config.body_json, config.params_json
        ]).encode()).hexdigest()
        return cls("latest-v1:" + key)


class ServicePoller:
    def __init__(self, factory, recognition, tokens, config, stop=None, guard=None):
        self.factory, self.recognition, self.tokens, self.config = factory, recognition, tokens, config
        self.stop = stop or Event()
        self.guard = guard or (lambda: None)
        self.store = RecognitionStore(factory)

    def initialize(self):
        with self.factory() as db, db.begin():
            state = db.get(ServiceSync, 1)
            if state is None:
                state = ServiceSync(id=1, config_key=self.config.fingerprint)
                db.add(state)
            elif state.config_key and state.config_key.startswith("latest-v1:") and state.config_key != self.config.fingerprint:
                raise ValueError("Worker тохиргоо хадгалсан явцтай зөрж байна. Явцыг шалгаж шинэчилнэ үү.")
            elif state.config_key != self.config.fingerprint:
                # Upgrade the old date-window poller without deleting recognition history.
                state.next_request_at = max(aware(state.next_request_at) or now_utc(),
                                            now_utc() + timedelta(seconds=INTERVAL))
                state.config_key = self.config.fingerprint
                state.failures = 0
            state.window_start = state.window_end = None
            state.next_offset = 0
            state.status, state.last_error = "waiting", None
            state.heartbeat_at = now_utc()
            # Only performed after obtaining the exclusive worker lock.
            db.execute(update(Row).where(Row.status == "processing").values(
                status="failed", last_error="Worker тасарсан; дахин оролдоно.",
                completed_at=now_utc()))

    def tick(self):
        self.guard()
        now = now_utc()
        with self.factory() as db, db.begin():
            state = db.get(ServiceSync, 1)
            state.heartbeat_at = now
            if state.status == "blocked":
                return
            if state.status == "cooldown" and state.next_request_at and aware(state.next_request_at) > now:
                return
            due = not state.next_request_at or aware(state.next_request_at) <= now
            if due:
                # Reserve before network I/O, including across restarts.
                state.next_request_at = now + timedelta(seconds=INTERVAL)
                state.status = "fetching"
        if due:
            try:
                records = fetch_records(PAGE_SIZE, self.tokens, overrides={
                    "offset": 0, "limit": PAGE_SIZE,
                }, refresh_on_401=False, omit_date_filters=True)
                self.save_page(records)
            except ServiceComparisonError as error:
                with self.factory() as db, db.begin():
                    state = db.get(ServiceSync, 1)
                    state.failures += 1
                    state.last_error = str(error)
                    state.status = "blocked" if error.blocked else "cooldown"
                    delay = max(INTERVAL * min(2, 2 ** min(state.failures - 1, 4)), error.retry_after)
                    state.next_request_at = now_utc() + timedelta(seconds=delay)
                event("records.fetch.retry", logging.ERROR if error.blocked else logging.WARNING,
                      state=state.status, attempt=state.failures,
                      next_request_at=state.next_request_at, reason=str(error))
                return
        self.process_pending()
        if due:
            event("poll.completed", fetched=len(records), next_request_at=state.next_request_at)

    @operation("records.save")
    def save_page(self, records):
        inserted = 0
        try:
            values = [self.store.source_values(record) for record in records]
        except (ValueError, TypeError, AttributeError):
            raise ServiceComparisonError("Service бичлэгийн ID эсвэл огноо буруу. Хуудсыг алгасаагүй.", blocked=True)
        with self.factory() as db, db.begin():
            insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
            for value in values:
                result = db.execute(insert(Row).values(**value).on_conflict_do_nothing(
                    index_elements=[Row.source_record_id]).returning(Row.id))
                inserted += len(result.all())
            state = db.get(ServiceSync, 1)
            state.next_offset = 0
            state.last_success_at, state.last_error = now_utc(), None
            state.failures, state.status = 0, "waiting"

        event("records.saved", fetched=len(records), new=inserted, existing=len(records) - inserted)

    def process_pending(self):
        started = perf_counter()
        counts = dict(selected=0, succeeded=0, failed=0, skipped=0)
        try:
            self._process_pending(counts)
        finally:
            if counts["selected"]:
                with self.factory() as db:
                    state = db.get(ServiceSync, 1)
                    event("cycle.completed", **counts,
                          remaining=counts["selected"] - counts["succeeded"] - counts["failed"] - counts["skipped"],
                          state=state.status, next_request_at=state.next_request_at,
                          duration_ms=round((perf_counter() - started) * 1000))

    def _process_pending(self, counts):
        cutoff = now_utc() - timedelta(seconds=IMAGE_RETRY_INTERVAL)
        with self.factory() as db:
            rows = db.scalars(select(Row).where(
                Row.attempt_count < MAX_ATTEMPTS,
                or_(Row.status == "pending", (Row.status == "failed") & (Row.completed_at <= cutoff)),
            ).order_by(Row.fetched_at, Row.id).limit(PAGE_SIZE)).all()
            records = [{"_id": r.source_record_id, "plate": r.plate,
                        "event_date": aware(r.event_date).isoformat() if r.event_date else None,
                        "mark": r.source_mark, "model": r.source_model, "color": r.source_color,
                        "typeNameEng": r.source_type, "full_photo": r.source_image_path,
                        "_attempt": r.attempt_count + 1} for r in rows]
        counts["selected"] = len(records)
        for record in records:
            if self.stop.is_set():
                break
            self.guard()
            with self.factory() as db, db.begin():
                state = db.get(ServiceSync, 1)
                state.status, state.heartbeat_at = "processing", now_utc()
            if not self.store.start(record):
                counts["skipped"] += 1
                event("record.skipped", record_id=record["_id"], reason="already_processing")
                continue
            event("record.processing", record_id=record["_id"], attempt=record["_attempt"], max_attempts=MAX_ATTEMPTS)
            try:
                result = compare_one(record, self.recognition)
            except ServiceComparisonError as error:
                counts["failed"] += 1
                self.store.fail(record["_id"], str(error))
                self.log_retry(record, blocked=error.blocked, delay=max(IMAGE_RETRY_INTERVAL, error.retry_after, INTERVAL))
                if error.blocked or error.retry_after:
                    with self.factory() as db, db.begin():
                        state = db.get(ServiceSync, 1)
                        state.status = "blocked" if error.blocked else "cooldown"
                        state.last_error = str(error)
                        state.next_request_at = now_utc() + timedelta(seconds=max(INTERVAL, error.retry_after))
                    return
            except Exception as error:
                # No upstream URLs, credentials or model internals in user-facing errors.
                counts["failed"] += 1
                event("record.failed", logging.ERROR, record_id=record["_id"], error_type=type(error).__name__)
                self.store.fail(record["_id"], "Зураг татах эсвэл таних үед алдаа гарлаа.")
                self.log_retry(record)
            else:
                self.store.complete(record["_id"], result)
                counts["succeeded"] += 1
            if self.stop.wait(2):
                break
        with self.factory() as db, db.begin():
            state = db.get(ServiceSync, 1)
            state.status, state.heartbeat_at = "waiting", now_utc()

    def log_retry(self, record, blocked=False, delay=IMAGE_RETRY_INTERVAL):
        exhausted = record["_attempt"] >= MAX_ATTEMPTS
        event("record.retry_stopped" if blocked or exhausted else "record.retry_scheduled",
              logging.ERROR if blocked or exhausted else logging.WARNING,
              record_id=record["_id"], attempt=record["_attempt"], max_attempts=MAX_ATTEMPTS,
              reason="blocked" if blocked else "max_attempts" if exhausted else "processing_failed",
              retry_not_before=None if blocked or exhausted else now_utc() + timedelta(seconds=delay))
