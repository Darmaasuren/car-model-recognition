import os
from dataclasses import dataclass, field
from functools import lru_cache
import math
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

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

    recognition_url: str
    recognition_api_key: str
    recognition_timeout: float
    max_image_bytes: int
    max_image_pixels: int
    max_video_bytes: int
    max_video_seconds: float
    runtime_dir: Path
    upload_dir: Path
    crop_dir: Path
    full_photo_dir: Path
    output_dir: Path


def get_settings() -> Settings:
    return Settings(
        api_prefix=required_env("API_PREFIX"),
        api_key=required_env("API_KEY"),
        session_cookie="vehicle_session",
        session_seconds=max(60, int(os.getenv("SESSION_SECONDS", "28800"))),
        cookie_secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        cors_origins=parse_origins(os.getenv("CORS_ORIGINS")),
        recognition_url=os.getenv("RECOGNITION_URL", "http://localhost:8009/api/v1").rstrip("/"),
        recognition_api_key=os.getenv("RECOGNITION_API_KEY", "").strip() or required_env("API_KEY"),
        recognition_timeout=float(os.getenv("RECOGNITION_TIMEOUT_SECONDS", "120")),
        max_image_bytes=MAX_IMAGE_BYTES,
        max_image_pixels=MAX_IMAGE_PIXELS,
        max_video_bytes=MAX_VIDEO_BYTES,
        max_video_seconds=MAX_VIDEO_SECONDS,
        runtime_dir=RUNTIME_DIR,
        upload_dir=RUNTIME_DIR / "uploads",
        crop_dir=RUNTIME_DIR / "crops",
        full_photo_dir=RUNTIME_DIR / "full_photo",
        output_dir=RUNTIME_DIR / "outputs",
    )


# Load API-only requirements on demand; migration/admin tools do not need CORS/API keys.
@lru_cache(maxsize=1)
def _api_settings():
    return get_settings()


def __getattr__(name):
    if name == "settings":
        return _api_settings()
    raise AttributeError(name)



@dataclass(frozen=True)
class DatabaseSettings:
    username: str
    password: str = field(repr=False)
    host: str
    port: int
    name: str


def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings(os.getenv("DB_USER", "vehicle_app"), os.environ["DB_PASSWORD"],
                            os.getenv("DB_HOST", "localhost"), int(os.getenv("DB_PORT", "5432")),
                            os.getenv("DB_NAME", "vehicle_recognition"))


@dataclass(frozen=True)
class AdminSettings:
    username: str
    password: str = field(repr=False)


def get_admin_settings() -> AdminSettings:
    return AdminSettings(os.getenv("ADMIN_USERNAME", "").strip().lower(), os.getenv("ADMIN_PASSWORD", ""))


@dataclass(frozen=True)
class ComparisonSettings:
    url: str | None
    method: str
    body_json: str
    params_json: str
    token: str = field(repr=False)
    login_url: str
    username: str
    password: str = field(repr=False)
    password_hash: str = field(repr=False)
    image_base_url: str
    date_start_field: str
    date_end_field: str
    worker_enabled: bool


def get_comparison_settings() -> ComparisonSettings:
    # Keep raw request settings for the persisted worker fingerprint.
    return ComparisonSettings(
        url=os.getenv("SERVICE_URL"), method=os.getenv("SERVICE_METHOD", "POST"),
        body_json=os.getenv("SERVICE_BODY_JSON", "{}"), params_json=os.getenv("SERVICE_PARAMS_JSON", "{}"),
        token=os.getenv("SERVICE_TOKEN", "").strip().removeprefix("Bearer ").strip(),
        login_url=os.getenv("SERVICE_LOGIN_URL", "").strip(), username=os.getenv("SERVICE_USERNAME", "").strip(),
        password=os.getenv("SERVICE_PASSWORD", ""), password_hash=os.getenv("SERVICE_PASSWORD_SHA256", "").strip(),
        image_base_url=os.getenv("IMAGE_BASE_URL", "").strip().rstrip("/"),
        date_start_field=os.getenv("SERVICE_DATE_START_FIELD", "startDate"),
        date_end_field=os.getenv("SERVICE_DATE_END_FIELD", "endDate"),
        worker_enabled=os.getenv("SERVICE_WORKER_ENABLED", "false").lower() == "true",
    )


@dataclass(frozen=True)
class SeatbeltSettings:
    enabled: bool = False
    url: str = "http://host.docker.internal:8011"
    timeout: float = 30
    front_conf: float = .80
    conf: float = .25
    api_key: str = field(default="", repr=False)
    windshield_model_version: str = "unknown"
    seatbelt_model_version: str = "unknown"

    def __post_init__(self):
        if not math.isfinite(self.timeout) or self.timeout <= 0 or not all(
            math.isfinite(x) and .01 <= x <= 1 for x in (self.front_conf, self.conf)
        ):
            raise ValueError("Invalid seatbelt timeout or confidence configuration")


def get_seatbelt_settings() -> SeatbeltSettings:
    return SeatbeltSettings(
        enabled=os.getenv("SEATBELT_ENABLED", "false").lower() == "true",
        url=os.getenv("SEATBELT_URL", "http://host.docker.internal:8011").rstrip("/"),
        timeout=float(os.getenv("SEATBELT_TIMEOUT_SECONDS", "30")),
        front_conf=float(os.getenv("SEATBELT_FRONT_VIEW_MIN_CONFIDENCE", "0.90")),
        conf=float(os.getenv("SEATBELT_CONFIDENCE", "0.25")),
        api_key=os.getenv("SEATBELT_API_KEY", ""),
        windshield_model_version=os.getenv("WINDSHIELD_MODEL_VERSION", "unknown"),
        seatbelt_model_version=os.getenv("SEATBELT_MODEL_VERSION", "unknown"),
    )
