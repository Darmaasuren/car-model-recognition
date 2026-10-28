"""Short transactions around the existing synchronous comparison workflow."""
from datetime import datetime, timezone
from app.core.observability import event, operation
from pathlib import Path

from sqlalchemy import update, select, func, case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import settings
from app.models.user import utcnow
from app.models.sync_state import ServiceSync
from app.models.recognition import VehicleRecognition as Row


class RecognitionStore:
    def __init__(self, factory):
        self.factory = factory

    def source_values(self, record):
        record_id = str(record.get("_id") or "").strip()
        if not record_id:
            raise ValueError("Service-ийн _id байхгүй байна.")
        event_date = record.get("event_date")
        if event_date:
            event_date = datetime.fromisoformat(str(event_date).replace("Z", "+00:00"))
            if event_date.tzinfo is None:
                raise ValueError("event_date цагийн бүсгүй байна.")
        return dict(
            source_record_id=record_id, event_date=event_date or None,
            **{column: str(record.get(key) or "") for column, key in {
                "plate": "plate", "source_mark": "mark", "source_model": "model",
                "source_color": "color", "source_type": "typeNameEng",
                "source_image_path": "full_photo",
            }.items()},
        )

    def enqueue(self, record):
        values = self.source_values(record)
        with self.factory() as db, db.begin():
            insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
            db.execute(insert(Row).values(**values).on_conflict_do_nothing(
                index_elements=[Row.source_record_id]))

    def start(self, record):
        values = self.source_values(record)
        with self.factory() as db, db.begin():
            result = db.execute(update(Row).where(
                Row.source_record_id == values["source_record_id"], Row.status != "processing",
            ).values(
                **values, status="processing", attempt_count=Row.attempt_count + 1,
                started_at=utcnow(), completed_at=None, last_error=None,
                prediction=None, comparison=None, vehicle_bbox=None,
                local_image_path=None, image_width=None, image_height=None,
                model_version=None,
                seatbelt_result=case(
                    (Row.seatbelt_result["schemaVersion"].as_integer() == 1, None),
                    else_=Row.seatbelt_result),
            ))
            return result.rowcount == 1

    @operation("record.save")
    def complete(self, record_id, result):
        prediction = result.get("prediction")
        bbox = prediction.get("vehicleBbox") if prediction else None
        with self.factory() as db, db.begin():
            db.execute(update(Row).where(Row.source_record_id == record_id).values(
                status="completed", completed_at=utcnow(), prediction=prediction,
                model_version=result.get("modelVersion"),
                **({"seatbelt_result": prediction["seatbelt"]} if prediction and (prediction.get("seatbelt") or {}).get("schemaVersion") == 1 else {}),
                comparison={key: result.get(key) for key in (
                    "imageStatus", "modelStatus", "colorStatus", "typeStatus", "viewStatus")},
                vehicle_bbox=({"coordinateSpace": "original_image", "units": "pixels",
                               "bboxFormat": "xyxy", "box": bbox} if bbox else None),
                local_image_path=str(Path("full_photo") / result["imageUrl"].rsplit("/", 1)[-1]),
                image_width=result["imageWidth"], image_height=result["imageHeight"],
            ))

        event("record.saved", record_id=record_id, status="completed")

    @operation("record.save_failure")
    def fail(self, record_id, message):
        with self.factory() as db, db.begin():
            db.execute(update(Row).where(Row.source_record_id == record_id).values(
                status="failed", last_error=message, completed_at=utcnow()))

    def list_results(self, offset=0, limit=20):
        with self.factory() as db:
            total = db.scalar(select(func.count()).select_from(Row))
            rows = db.scalars(select(Row).order_by(
                func.coalesce(Row.started_at, Row.fetched_at).desc(), Row.id.desc(),
            ).offset(offset).limit(limit)).all()
            items = []
            for row in rows:
                comparison = row.comparison or {}
                image_url = None
                if row.local_image_path:
                    path = (settings.runtime_dir / row.local_image_path).resolve()
                    # Keep historical records in crops/ accessible.
                    allowed_dirs = (settings.full_photo_dir, settings.runtime_dir / "crops")
                    if path.is_file() and path.parent in allowed_dirs:
                        image_url = f"/media/{path.parent.name}/{path.name}"
                items.append({
                    "recordId": row.source_record_id, "plate": row.plate,
                    "eventDate": row.event_date.isoformat() if row.event_date else "",
                    "sourceMark": row.source_mark, "sourceModel": row.source_model,
                    "sourceColor": row.source_color, "sourceType": row.source_type,
                    "status": row.status, "imageUrl": image_url,
                    "prediction": ({key: value for key, value in row.prediction.items()
                                    if key != "seatbelt"} | ({"seatbelt": row.seatbelt_result}
                                    if (row.seatbelt_result or {}).get("schemaVersion") == 1 else {})
                                    if row.prediction is not None else None),
                    "error": row.last_error,
                    **{key: comparison.get(key) or row.status for key in (
                        "imageStatus", "modelStatus", "colorStatus", "typeStatus", "viewStatus")},
                })
            return {"items": items, "count": len(items), "total": total,
                    "offset": offset, "limit": limit}


def read_status(factory):
    with factory() as db:
        state = db.get(ServiceSync, 1)
        counts = dict(db.execute(select(Row.status, func.count()).group_by(Row.status)).all())
        if state is None:
            return {"status": "not_started", "counts": counts}
        status = state.status
        heartbeat = state.heartbeat_at
        if heartbeat is not None and heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        if heartbeat is None or (utcnow() - heartbeat).total_seconds() > 180:
            status = "unresponsive"
        return {"status": status, "counts": counts, "error": state.last_error,
                "nextRequestAt": state.next_request_at,
                "lastSuccessAt": state.last_success_at, "windowStart": state.window_start,
                "windowEnd": state.window_end, "offset": state.next_offset}
