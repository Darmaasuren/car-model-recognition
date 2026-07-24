from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import health, inference, live
from config import settings
from services.classifier import VehicleClassifier
from services.detector import VehicleDetector
from services.live_manager import LiveManager
from services.media import MediaService
from services.pipeline import RecognitionPipeline
from services.video_manager import VideoSessionManager


settings.runtime_dir.mkdir(
    parents=True,
    exist_ok=True,
)
settings.crop_dir.mkdir(
    parents=True,
    exist_ok=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    yield

    if app.state.live_manager is not None:
        app.state.live_manager.stop_all()
    if app.state.video_manager is not None:
        app.state.video_manager.stop_all()


app = FastAPI(
    title="Vehicle Recognition API",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {
        "name": "Vehicle Recognition API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/media/crops",
    StaticFiles(directory=settings.crop_dir),
    name="crops",
)

app.include_router(
    health.router,
    prefix=settings.api_prefix,
    tags=["health"],
)
app.include_router(
    inference.router,
    prefix=settings.api_prefix,
    tags=["inference"],
)
app.include_router(
    live.router,
    prefix=settings.api_prefix,
    tags=["live"],
)
