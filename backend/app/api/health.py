from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.services.recognition.client import RecognitionServiceError

router = APIRouter()


@router.get("/health")
def health(request: Request):
    try:
        ready = request.app.state.recognition_client.health().get("modelReady", False)
    except RecognitionServiceError:
        ready = False
    return JSONResponse({"status": "ok" if ready else "degraded", "modelReady": ready,
                         "modelError": None if ready else "Recognition service unavailable"},
                        status_code=200 if ready else 503)
