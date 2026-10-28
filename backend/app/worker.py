"""Run with python -m app.worker. A PostgreSQL lock allows only one worker."""
import logging
from app.core.observability import configure_logging, event
import signal
from threading import Event

from sqlalchemy import text
from app.services.seatbelt import SeatbeltService
from app.core.database import upgrade_database, make_database
from app.models.sync_state import ServiceSync
from app.models.user import utcnow
from app.services.comparison.auth import ServiceTokenProvider
from app.services.comparison.poller import PollConfig, ServicePoller

log = logging.getLogger(__name__)


def build_recognition():
    from app.core.config import settings
    from app.services.media import MediaService
    from app.services.recognition.client import RecognitionClient
    from app.services.recognition.results import RecognitionResults
    media = MediaService(upload_dir=settings.upload_dir, crop_dir=settings.crop_dir,
                         output_dir=settings.output_dir)
    return RecognitionResults(media, RecognitionClient(), SeatbeltService())


def main():
    logging.basicConfig(level=logging.INFO)
    configure_logging()
    stop = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    engine, factory = make_database()
    try:
        # Hold one dedicated session-level lock throughout the worker's lifetime.
        with engine.connect() as lock:
            acquired = lock.scalar(text("SELECT pg_try_advisory_lock(731904822)"))
            lock.commit()
            if not acquired:
                log.info("Another service worker is already running.")
                return
            upgrade_database(engine)
            try:
                config = PollConfig.from_env()
            except ValueError as error:
                with factory() as db, db.begin():
                    state = db.get(ServiceSync, 1)
                    if state is None:
                        state = ServiceSync(id=1)
                        db.add(state)
                    state.status, state.last_error = "blocked", str(error)
                    state.heartbeat_at = utcnow()
                log.error("Worker configuration is incomplete; no service requests will be sent.")
                # Avoid restart loops and repeated requests with missing configuration.
                while not stop.wait(30):
                    with factory() as db, db.begin():
                        db.get(ServiceSync, 1).heartbeat_at = utcnow()
                return

            def guard():
                if lock.invalidated or lock.closed:
                    raise RuntimeError("Worker database lock connection lost")
                lock.execute(text("SELECT 1"))
                lock.commit()

            poller = ServicePoller(factory, None, ServiceTokenProvider(factory), config, stop, guard)
            try:
                poller.initialize()
            except ValueError as error:
                with factory() as db, db.begin():
                    state = db.get(ServiceSync, 1)
                    state.status, state.last_error = "blocked", str(error)
                log.error("Worker configuration differs from its saved cursor.")
                while not stop.wait(30):
                    guard()
                    with factory() as db, db.begin():
                        db.get(ServiceSync, 1).heartbeat_at = utcnow()
                return
            with factory() as db, db.begin():
                db.get(ServiceSync, 1).status = "starting"
            poller.recognition = build_recognition()
            event("worker.started", page_size=20, interval_seconds=1200, date_filters=False)
            while not stop.is_set():
                poller.tick()
                stop.wait(5)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
