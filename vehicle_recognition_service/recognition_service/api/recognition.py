"""Image, vehicle bbox and plate inference endpoints."""
from uuid import uuid4

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from recognition_service.config import settings
from recognition_service.media import decode_base64_image, decode_image_bytes
from recognition_service.inference.pipeline import PlateProcessStatus
from recognition_service.inference.pipeline import classify_vehicle_bbox
from recognition_service.schemas.recognition import (BoundingBox, InferenceResponse, PlateVehicleRequest, PlateVehicleResponse,
                         VehicleBboxRequest, VehicleBboxResponse)
from recognition_service.api.security import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


async def read_image(file):
    try:
        data = await file.read(settings.max_image_bytes + 1)
        return await run_in_threadpool(decode_image_bytes, data)
    except (ValueError, cv2.error) as error:
        raise HTTPException(422, "Зураг уншигдахгүй байна.") from error
    finally:
        await file.close()


async def read_base64(value):
    try:
        return await run_in_threadpool(decode_base64_image, value)
    except (ValueError, cv2.error) as error:
        raise HTTPException(422, "Base64 зураг буруу байна.") from error


def bbox_from_form(x1, y1, x2, y2):
    try:
        return BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
    except ValidationError as error:
        raise HTTPException(422, "Bbox координат буруу байна.") from error


def check_bounds(frame, bbox):
    height, width = frame.shape[:2]
    if not (0 <= bbox.x1 < bbox.x2 <= width and 0 <= bbox.y1 < bbox.y2 <= height):
        raise HTTPException(422, "Bbox зургийн хэмжээнээс гарсан байна.")


def classify(request, frame, bbox, event_id):
    check_bounds(frame, bbox)
    with request.app.state.inference_lock:
        result = classify_vehicle_bbox(request.app.state.classifier, frame, bbox)
    return VehicleBboxResponse(event_id=event_id or uuid4().hex, vehicle_bbox=bbox, result=result,
                              reason_code=None if result else "CLASSIFICATION_FAILED")


def plate(request, frame, bbox, event_id):
    check_bounds(frame, bbox)
    with request.app.state.inference_lock:
        outcome = request.app.state.pipeline.process_plate_event(frame, bbox)
    return PlateVehicleResponse(event_id=event_id or uuid4().hex, plate_bbox=bbox,
        matched=outcome.status == PlateProcessStatus.MATCHED, vehicle_bbox=outcome.vehicle_bbox,
        match_score=outcome.match_score, result=outcome.result,
        reason_code=None if outcome.status == PlateProcessStatus.MATCHED else outcome.status.value)


@router.post("/inference/image", response_model=InferenceResponse)
async def image(request: Request, file: UploadFile = File(...)):
    frame = await read_image(file)
    def infer():
        with request.app.state.inference_lock:
            return request.app.state.pipeline.process_image(frame)
    return InferenceResponse(results=await run_in_threadpool(infer),
                             model_version=settings.model_version,
                             label_groups=request.app.state.classifier.label_groups)


@router.post("/inference/vehicle", response_model=VehicleBboxResponse, response_model_exclude_none=True)
async def vehicle(request: Request, payload: VehicleBboxRequest):
    return await run_in_threadpool(classify, request, await read_base64(payload.image_base64),
                                  payload.vehicle_bbox, payload.event_id)


@router.post("/inference/vehicle/upload", response_model=VehicleBboxResponse, response_model_exclude_none=True)
async def vehicle_upload(request: Request, file: UploadFile = File(...), event_id: str | None = Form(None),
                         vehicle_x1: int = Form(...), vehicle_y1: int = Form(...),
                         vehicle_x2: int = Form(...), vehicle_y2: int = Form(...)):
    frame = await read_image(file)
    bbox = bbox_from_form(vehicle_x1, vehicle_y1, vehicle_x2, vehicle_y2)
    return await run_in_threadpool(classify, request, frame, bbox, event_id)


@router.post("/inference/plate", response_model=PlateVehicleResponse, response_model_exclude_none=True)
async def plate_image(request: Request, payload: PlateVehicleRequest):
    return await run_in_threadpool(plate, request, await read_base64(payload.image_base64),
                                  payload.plate_bbox, payload.event_id)


@router.post("/inference/plate/upload", response_model=PlateVehicleResponse, response_model_exclude_none=True)
async def plate_upload(request: Request, file: UploadFile = File(...), event_id: str | None = Form(None),
                       plate_x1: int = Form(...), plate_y1: int = Form(...),
                       plate_x2: int = Form(...), plate_y2: int = Form(...)):
    frame = await read_image(file)
    bbox = bbox_from_form(plate_x1, plate_y1, plate_x2, plate_y2)
    return await run_in_threadpool(plate, request, frame, bbox, event_id)


