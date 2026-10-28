from dataclasses import dataclass
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("API_KEY", "")
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1").rstrip("/")
    model_path: Path = Path(os.getenv("MODEL_PATH", str(ROOT / "checkpoints/best_loss_model_v3.pt")))
    detector_model_path: Path = Path(os.getenv("DETECTOR_MODEL_PATH", str(ROOT / "checkpoints/yolo11s.pt")))
    model_version: str = os.getenv("MODEL_VERSION", "best_loss_model_v3")
    detector_confidence: float = float(os.getenv("DETECTOR_CONFIDENCE", "0.2"))
    device: str = os.getenv("MODEL_DEVICE", "auto")
    runtime_dir: Path = Path(os.getenv("RUNTIME_DIR", str(ROOT / "runtime")))
    max_image_bytes: int = 15_728_640
    max_image_pixels: int = 12_000_000
    max_video_bytes: int = 209_715_200
    max_video_seconds: float = 360
    max_sessions: int = max(1, int(os.getenv("MAX_TRACKING_SESSIONS", "2")))
    session_ttl: int = max(30, int(os.getenv("SESSION_TTL_SECONDS", "600")))
    max_events: int = 100
    event_buffer_bytes: int = 64 * 1024 * 1024
    roi: tuple = tuple(float(v) for v in os.getenv("TRACKING_ROI", "0.20,0.60,1.00,0.97").split(","))

    @property
    def camera_sources(self):
        return {"camera-1": os.getenv("CAMERA_1_SOURCE", "").strip()}


settings = Settings()
