from fastapi import APIRouter, HTTPException, Request, Query
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from app.services.service_comparison import ServiceComparisonError, compare_batch, compare_next

router = APIRouter(prefix="/service", tags=["service"])


@router.post("/compare-next")
async def compare_next_record(request: Request):
    pipeline = request.app.state.pipeline
    if pipeline is None:
        raise HTTPException(503, request.app.state.model_error or "Model бэлэн биш байна.")
    try:
        return await run_in_threadpool(compare_next, pipeline, request.app.state.service_tokens, request.app.state.db_sessions)
    except SQLAlchemyError as error:
        raise HTTPException(503, "Database-д хадгалж чадсангүй. Дахин оролдоно уу.") from error
    except ServiceComparisonError as error:
        raise HTTPException(502, str(error)) from error


@router.post("/compare-batch")
async def compare_batch_records(request: Request):
    pipeline = request.app.state.pipeline
    if pipeline is None:
        raise HTTPException(503, request.app.state.model_error or "Model бэлэн биш байна.")
    try:
        return await run_in_threadpool(compare_batch, pipeline, request.app.state.service_tokens, request.app.state.db_sessions)
    except SQLAlchemyError as error:
        raise HTTPException(503, "Database-д хадгалж чадсангүй. Дахин оролдоно уу.") from error
    except ServiceComparisonError as error:
        raise HTTPException(502, str(error)) from error


@router.get("/comparisons")
async def list_comparisons(request: Request, offset: int = Query(0, ge=0),
                           limit: int = Query(20, ge=1, le=100)):
    from app.services.recognition_store import RecognitionStore

    try:
        return await run_in_threadpool(
            RecognitionStore(request.app.state.db_sessions).list_results, offset, limit)
    except SQLAlchemyError as error:
        raise HTTPException(503, "Хадгалсан мэдээллийг уншиж чадсангүй.") from error
