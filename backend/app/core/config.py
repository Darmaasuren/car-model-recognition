import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DETECTOR_MODEL_PATH = (
    BACKEND_ROOT / "checkpoints/detector/yolo11s.pt"
).resolve()
CLASSIFIER_MODEL_PATH = (
    BACKEND_ROOT
    / "checkpoints/classifier/best_loss_model_v3.pt"
).resolve()
MODEL_DEVICE = "cpu"
DETECTOR_CONFIDENCE = 0.2

MAX_IMAGE_BYTES = 15_728_640
MAX_IMAGE_PIXELS = 12_000_000
MAX_VIDEO_BYTES = 209_715_200
MAX_VIDEO_SECONDS = 360.0

RUNTIME_DIR = (BACKEND_ROOT / "runtime").resolve()


def parse_origins(value: str | None) -> tuple[str, ...]:
    if value is None:
        raise ValueError(
            "CORS_ORIGINS environment variable тохируулаагүй байна."
        )

    origins = tuple(
        origin.strip()
        for origin in value.split(",")
        if origin.strip()
    )

    if not origins:
        raise ValueError(
            "CORS_ORIGINS environment variable хоосон байна."
        )

    return origins


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise ValueError(
            f"{name} environment variable тохируулаагүй байна."
        )

    return value


@dataclass(frozen=True)
class Settings:
    api_prefix: str
    cors_origins: tuple[str, ...]
    api_key: str
    session_cookie: str
    session_seconds: int
    cookie_secure: bool

    detector_model_path: Path
    classifier_model_path: Path
    detector_confidence: float
    device: str
    max_image_bytes: int
    max_image_pixels: int
    max_video_bytes: int
    max_video_seconds: float
    runtime_dir: Path
    upload_dir: Path
    crop_dir: Path
    output_dir: Path
    camera_sources: dict[str, str]


def get_settings() -> Settings:
    return Settings(
        api_prefix=required_env("API_PREFIX"),
        api_key=required_env("API_KEY"),
        session_cookie="vehicle_session",
        session_seconds=max(60, int(os.getenv("SESSION_SECONDS", "28800"))),
        cookie_secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        cors_origins=parse_origins(os.getenv("CORS_ORIGINS")),
        detector_model_path=DETECTOR_MODEL_PATH,
        classifier_model_path=CLASSIFIER_MODEL_PATH,
        detector_confidence=DETECTOR_CONFIDENCE,
        device=MODEL_DEVICE,
        max_image_bytes=MAX_IMAGE_BYTES,
        max_image_pixels=MAX_IMAGE_PIXELS,
        max_video_bytes=MAX_VIDEO_BYTES,
        max_video_seconds=MAX_VIDEO_SECONDS,
        runtime_dir=RUNTIME_DIR,
        upload_dir=RUNTIME_DIR / "uploads",
        crop_dir=RUNTIME_DIR / "crops",
        output_dir=RUNTIME_DIR / "outputs",
        camera_sources={
            "camera-1": os.getenv("CAMERA_1_SOURCE", "").strip(),
        },
    )


settings = get_settings()
