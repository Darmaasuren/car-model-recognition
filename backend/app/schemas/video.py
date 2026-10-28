from typing import Literal
from app.schemas.common import ApiModel
from app.schemas.recognition import RecognitionResult


class VideoSessionResponse(ApiModel):
    session_id: str


class VideoRecognitionEvent(ApiModel):
    type: Literal["recognition"] = "recognition"
    session_id: str
    result: RecognitionResult


class VideoStatusEvent(ApiModel):
    type: Literal["status"] = "status"
    session_id: str
    status: Literal[
        "pending",
        "running",
        "completed",
        "error",
        "stopped",
    ]
    error: str | None = None


