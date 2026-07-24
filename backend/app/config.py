import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")

def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (BACKEND_ROOT / path).resolve()


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
    runtime_dir = resolve_path(os.getenv("RUNTIME_DIR", "runtime"))

    return Settings(
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        api_key=required_env("API_KEY"),
        cors_origins=parse_origins(os.getenv("CORS_ORIGINS")),
        detector_model_path=resolve_path(
            os.getenv(
                "DETECTOR_MODEL_PATH",
                "../train/models/detector/yolo11n.pt",
            )
        ),
        classifier_model_path=resolve_path(
            os.getenv(
                "CLASSIFIER_MODEL_PATH",
                "../train/checkpoints/best_model.pt",
            )
        ),
        detector_confidence=float(os.getenv("DETECTOR_CONFIDENCE", "0.4")),
        device=os.getenv("MODEL_DEVICE", "auto"),
        max_image_bytes=int(
            os.getenv("MAX_IMAGE_BYTES", str(15 * 1024 * 1024))
        ),
        max_image_pixels=int(
            os.getenv("MAX_IMAGE_PIXELS", "12000000")
        ),
        max_video_bytes=int(
            os.getenv("MAX_VIDEO_BYTES", str(200 * 1024 * 1024))
        ),
        max_video_seconds=float(os.getenv("MAX_VIDEO_SECONDS", "120")),
        runtime_dir=runtime_dir,
        upload_dir=runtime_dir / "uploads",
        crop_dir=runtime_dir / "crops",
        output_dir=runtime_dir / "outputs",
        camera_sources={
            "camera-1": os.getenv("CAMERA_1_SOURCE", "").strip(),
        },
    )


settings = get_settings()
