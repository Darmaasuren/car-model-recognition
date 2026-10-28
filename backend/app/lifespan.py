from app.core.observability import configure_logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

import app.models.user
import app.models.recognition
import app.models.sync_state
import app.models.video_session
from app.core.config import settings
from app.core.database import upgrade_database, make_database
from app.services.auth import ensure_initial_admin
from app.services.comparison.auth import ServiceTokenProvider
from app.services.media import MediaService
from app.services.seatbelt import SeatbeltService
from app.services.recognition.client import RecognitionClient
from app.services.recognition.results import RecognitionResults
from app.services.recognition.video import VideoSessionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    engine, app.state.db_sessions = make_database()
    try:
        upgrade_database(engine)
        ensure_initial_admin(app.state.db_sessions)
        app.state.service_tokens = ServiceTokenProvider(app.state.db_sessions)
        app.state.media = MediaService(settings.upload_dir, settings.crop_dir, settings.output_dir)
        app.state.recognition_client = RecognitionClient()
        app.state.recognition = RecognitionResults(app.state.media, app.state.recognition_client, SeatbeltService())
        app.state.video_manager = VideoSessionManager(app.state.recognition_client, app.state.recognition, app.state.db_sessions)
        yield
    finally:
        # Recognition owns active jobs; its TTL reclaims orphaned sessions.
        engine.dispose()
