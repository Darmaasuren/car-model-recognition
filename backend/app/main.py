from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from app.services.recognition.client import RecognitionServiceError

from app.core.config import settings
from app.lifespan import lifespan
from app.api import auth, health, recognition, video, live, comparison
from app.middleware.auth import AuthMiddleware


settings.crop_dir.mkdir(parents=True, exist_ok=True)
windshield_dir = settings.crop_dir.parent / "windshields"
windshield_dir.mkdir(parents=True, exist_ok=True)
settings.full_photo_dir.mkdir(parents=True, exist_ok=True)
legacy_crop_dir = settings.runtime_dir / "crops"
legacy_crop_dir.mkdir(parents=True, exist_ok=True)


app = FastAPI(
    title="Vehicle Recognition API",
    lifespan=lifespan,
)


@app.exception_handler(RecognitionServiceError)
async def recognition_error(request, error):
    return JSONResponse({"detail": str(error)}, status_code=error.status_code)


@app.get("/")
def root():
    return {
        "name": "Vehicle Recognition API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }

app.add_middleware(AuthMiddleware)
app.include_router(auth.router, prefix=settings.api_prefix)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

person_dir = settings.crop_dir.parent / "persons"
person_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/persons", StaticFiles(directory=person_dir), name="persons")

app.mount(
    "/media/windshields",
    StaticFiles(directory=windshield_dir),
    name="windshields",
)

app.mount(
    "/media/crop",
    StaticFiles(directory=settings.crop_dir),
    name="crop",
)
app.mount(
    "/media/full_photo",
    StaticFiles(directory=settings.full_photo_dir),
    name="full_photo",
)
app.mount(
    "/media/crops",
    StaticFiles(directory=legacy_crop_dir),
    name="crops",
)

app.include_router(
    health.router,
    prefix=settings.api_prefix,
    tags=["health"],
)
app.include_router(
    recognition.router,
    prefix=settings.api_prefix,
    tags=["inference"],
)
app.include_router(
    live.router,
    prefix=settings.api_prefix,
    tags=["live"],
)
app.include_router(comparison.router, prefix=settings.api_prefix)

app.include_router(video.router, prefix=settings.api_prefix)
