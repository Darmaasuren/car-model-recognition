from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from recognition_service.config import settings
from recognition_service.api.security import require_api_key

router = APIRouter()


@router.get("/health")
def health(request: Request):
    ready = getattr(request.app.state, "pipeline", None) is not None
    return JSONResponse({"status": "ok" if ready else "unavailable", "modelReady": ready}, status_code=200 if ready else 503)


@router.get("/metadata", dependencies=[Depends(require_api_key)])
def metadata(request: Request):
    return {"modelVersion": settings.model_version, "labelGroups": request.app.state.classifier.label_groups}


