from fastapi import APIRouter, Request

from app.schemas.common import HealthResponse


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
)
def health(request: Request):
    model_ready = (
        request.app.state.pipeline is not None
    )

    return HealthResponse(
        status="ok",
        model_ready=model_ready,
        model_error=request.app.state.model_error,
    )
