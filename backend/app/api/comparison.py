from app.core.config import get_comparison_settings
from fastapi import APIRouter, HTTPException, Request, Query
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError

from app.services.comparison.compare import compare_batch, compare_next
from app.services.comparison.source import ServiceComparisonError
from app.services.comparison.store import RecognitionStore, read_status
from app.schemas.comparison import ComparisonResult, ComparisonBatch, ComparisonHistory, WorkerStatus

router = APIRouter(prefix="/service", tags=["service"])


@router.post("/compare-next", response_model=ComparisonResult, response_model_exclude_unset=True)
async def compare_next_record(request: Request):
    if get_comparison_settings().worker_enabled:
        raise HTTPException(409, "Автомат worker ажиллаж байгаа тул гараар хүсэлт явуулахгүй.")
    recognition = request.app.state.recognition
    if recognition is None:
        raise HTTPException(503, "Recognition service бэлэн биш байна.")
    try:
        return await run_in_threadpool(compare_next, recognition, request.app.state.service_tokens, request.app.state.db_sessions)
    except SQLAlchemyError as error:
        raise HTTPException(503, "Database-д хадгалж чадсангүй. Дахин оролдоно уу.") from error
    except ServiceComparisonError as error:
        raise HTTPException(502, str(error)) from error


@router.post("/compare-batch", response_model=ComparisonBatch, response_model_exclude_unset=True)
async def compare_batch_records(request: Request):
    if get_comparison_settings().worker_enabled:
        raise HTTPException(409, "Автомат worker ажиллаж байгаа тул гараар хүсэлт явуулахгүй.")
    recognition = request.app.state.recognition
    if recognition is None:
        raise HTTPException(503, "Recognition service бэлэн биш байна.")
    try:
        return await run_in_threadpool(compare_batch, recognition, request.app.state.service_tokens, request.app.state.db_sessions)
    except SQLAlchemyError as error:
        raise HTTPException(503, "Database-д хадгалж чадсангүй. Дахин оролдоно уу.") from error
    except ServiceComparisonError as error:
        raise HTTPException(502, str(error)) from error


@router.get("/comparisons", response_model=ComparisonHistory, response_model_exclude_unset=True)
async def list_comparisons(request: Request, offset: int = Query(0, ge=0),
                           limit: int = Query(20, ge=1, le=100)):

    try:
        return await run_in_threadpool(
            RecognitionStore(request.app.state.db_sessions).list_results, offset, limit)
    except SQLAlchemyError as error:
        raise HTTPException(503, "Хадгалсан мэдээллийг уншиж чадсангүй.") from error


@router.get("/worker-status", response_model=WorkerStatus, response_model_exclude_unset=True)
async def worker_status(request: Request):
    try:
        return await run_in_threadpool(read_status, request.app.state.db_sessions)
    except SQLAlchemyError as error:
        raise HTTPException(503, "Worker-ийн төлөвийг уншиж чадсангүй.") from error
