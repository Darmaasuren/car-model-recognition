from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models.user_model  # Register database tables before create_all.
import app.models.vehicle_recognition
import app.models.service_sync
from app.core.config import settings
from app.core.database import create_tables, make_database
from app.services.service_auth import ServiceTokenProvider
from app.services.classifier import VehicleClassifier
from app.services.detector import VehicleDetector
from app.services.live_manager import LiveManager
from app.services.media import MediaService
from app.services.pipeline import RecognitionPipeline
from app.services.video_manager import VideoSessionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    engine, app.state.db_sessions = make_database()
    try:
        create_tables(engine)
    except Exception:
        engine.dispose()
        raise
    app.state.service_tokens = ServiceTokenProvider(app.state.db_sessions)
    media = MediaService(
        upload_dir=settings.upload_dir,
        crop_dir=settings.crop_dir,
        output_dir=settings.output_dir,
    )

    app.state.media = media
    app.state.pipeline = None
    app.state.live_manager = None
    app.state.video_manager = None
    app.state.model_error = None

    try:
        detector = VehicleDetector(
            model_path=settings.detector_model_path,
            confidence=settings.detector_confidence,
            device=settings.device,
        )

        classifier = VehicleClassifier(
            model_path=settings.classifier_model_path,
            device=settings.device,
        )

        pipeline = RecognitionPipeline(
            detector=detector,
            classifier=classifier,
            media=media,
        )

        app.state.pipeline = pipeline
        app.state.live_manager = LiveManager(
            pipeline=pipeline,
            camera_sources=settings.camera_sources,
        )
        app.state.video_manager = VideoSessionManager(
            pipeline=pipeline,
            media=media,
        )
    except Exception as error:
        app.state.model_error = str(error)

    try:
        yield
    finally:
        if app.state.live_manager is not None:
            app.state.live_manager.stop_all()
        if app.state.video_manager is not None:
            app.state.video_manager.stop_all()
        engine.dispose()
