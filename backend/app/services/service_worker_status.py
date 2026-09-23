from sqlalchemy import func, select
from app.models.service_sync import ServiceSync
from app.models.vehicle_recognition import VehicleRecognition as Row
from app.services.service_poller import aware, now_utc


def read_status(factory):
    with factory() as db:
        state = db.get(ServiceSync, 1)
        counts = dict(db.execute(select(Row.status, func.count()).group_by(Row.status)).all())
        if state is None:
            return {"status": "not_started", "counts": counts}
        status = state.status
        if not state.heartbeat_at or (now_utc() - aware(state.heartbeat_at)).total_seconds() > 180:
            status = "unresponsive"
        return {"status": status, "counts": counts, "error": state.last_error,
                "nextRequestAt": state.next_request_at,
                "lastSuccessAt": state.last_success_at, "windowStart": state.window_start,
                "windowEnd": state.window_end, "offset": state.next_offset}
