from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import require_api_key
from app.schemas.recognition import (
    BoundingBox, InferenceResponse, PlateVehicleRequest, PlateVehicleResponse,
    VehicleBboxRequest, VehicleBboxResponse,
)
from app.services.media import MediaTooLargeError

router = APIRouter(prefix="/inference")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


@router.post("/image", response_model=InferenceResponse)
async def recognize_image(request: Request, file: UploadFile = File(...)):
    media = request.app.state.media
    path = await media.save_upload(file, IMAGE_SUFFIXES, settings.max_image_bytes)
    try:
        try:
            frame = await run_in_threadpool(media.read_image, path)
        except MediaTooLargeError as error:
            raise HTTPException(413, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        results = await run_in_threadpool(request.app.state.recognition.process_image, frame)
        return InferenceResponse(results=results)
    finally:
        media.remove_file(path)


@router.post("/vehicle", response_model=PlateVehicleResponse, response_model_exclude_none=True,
             dependencies=[Depends(require_api_key)])
async def recognize_plate_vehicle_base64(request: Request, payload: PlateVehicleRequest):
    data = await run_in_threadpool(request.app.state.recognition_client.json, "POST", "/inference/plate",
                                   json=payload.model_dump(by_alias=True))
    return PlateVehicleResponse.model_validate(data)


@router.post("/vehicle/upload", response_model=PlateVehicleResponse, response_model_exclude_none=True,
             dependencies=[Depends(require_api_key)])
async def recognize_plate_vehicle_upload(request: Request, file: UploadFile = File(...),
    event_id: str | None = Form(None), plate_x1: int = Form(...), plate_y1: int = Form(...),
    plate_x2: int = Form(...), plate_y2: int = Form(...)):
    try:
        try:
            BoundingBox(x1=plate_x1, y1=plate_y1, x2=plate_x2, y2=plate_y2)
        except ValidationError as error:
            raise HTTPException(422, "Bbox координат буруу байна.") from error
        data = await file.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            raise HTTPException(413, "Зургийн хэмжээ хэтэрсэн.")
        result = await run_in_threadpool(request.app.state.recognition_client.json, "POST", "/inference/plate/upload",
            files={"file": ("image.png", data, file.content_type or "application/octet-stream")},
            data={"plate_x1": plate_x1, "plate_y1": plate_y1, "plate_x2": plate_x2, "plate_y2": plate_y2,
                  **({"event_id": event_id} if event_id else {})})
        return PlateVehicleResponse.model_validate(result)
    finally:
        await file.close()


@router.post("/vehicle-bbox", response_model=VehicleBboxResponse, response_model_exclude_none=True,
             dependencies=[Depends(require_api_key)])
async def recognize_vehicle_bbox(request: Request, payload: VehicleBboxRequest):
    result = await run_in_threadpool(request.app.state.recognition_client.json, "POST", "/inference/vehicle",
                                    json=payload.model_dump(by_alias=True))
    return VehicleBboxResponse.model_validate(result)


@router.post("/vehicle-bbox/upload", response_model=VehicleBboxResponse, response_model_exclude_none=True,
             dependencies=[Depends(require_api_key)])
async def recognize_vehicle_bbox_upload(request: Request, file: UploadFile = File(...),
    event_id: str | None = Form(None), vehicle_x1: int = Form(...), vehicle_y1: int = Form(...),
    vehicle_x2: int = Form(...), vehicle_y2: int = Form(...)):
    try:
        try:
            BoundingBox(x1=vehicle_x1, y1=vehicle_y1, x2=vehicle_x2, y2=vehicle_y2)
        except ValidationError as error:
            raise HTTPException(422, "Bbox координат буруу байна.") from error
        data = await file.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            raise HTTPException(413, "Зургийн хэмжээ хэтэрсэн.")
        result = await run_in_threadpool(request.app.state.recognition_client.json, "POST", "/inference/vehicle/upload",
            files={"file": ("image.png", data, file.content_type or "application/octet-stream")},
            data={"vehicle_x1": vehicle_x1, "vehicle_y1": vehicle_y1, "vehicle_x2": vehicle_x2, "vehicle_y2": vehicle_y2,
                  **({"event_id": event_id} if event_id else {})})
        return VehicleBboxResponse.model_validate(result)
    finally:
        await file.close()
