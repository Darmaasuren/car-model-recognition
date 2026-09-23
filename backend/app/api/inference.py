import asyncio
from pathlib import Path
from uuid import uuid4

import cv2
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from app.core.security import require_api_key
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.schemas.recognition import (
    BoundingBox,
    InferenceResponse,
    PlateVehicleRequest,
    PlateVehicleResponse,
    VideoRecognitionEvent,
    VideoSessionResponse,
    VideoStatusEvent,
)
from app.services.media import MediaTooLargeError
from app.services.seatbelt_client import enrich_results, recognize_file_image
from app.services.pipeline import (
    PlateProcessStatus,
    TrackingState,
)


router = APIRouter(prefix="/inference")
plate_inference_semaphore = asyncio.Semaphore(1)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv"}


def get_pipeline(request: Request):
    pipeline = request.app.state.pipeline

    if pipeline is None:
        raise HTTPException(
            status_code=503,
            detail=request.app.state.model_error
            or "Model бэлэн биш байна.",
        )

    return pipeline


def get_video_manager(request: Request):
    manager = request.app.state.video_manager

    if manager is None:
        raise HTTPException(
            status_code=503,
            detail=request.app.state.model_error
            or "Video manager бэлэн биш байна.",
        )

    return manager


def invalid_media(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


async def process_plate_frame(
    pipeline,
    frame,
    plate_bbox: BoundingBox,
    event_id: str | None,
    persist_crop: bool,
) -> PlateVehicleResponse:
    height, width = frame.shape[:2]

    if (
        plate_bbox.x1 < 0
        or plate_bbox.y1 < 0
        or plate_bbox.x2 > width
        or plate_bbox.y2 > height
    ):
        raise HTTPException(
            status_code=422,
            detail="Plate bbox зургийн хэмжээнээс гарсан байна.",
        )

    async with plate_inference_semaphore:
        outcome = await run_in_threadpool(
            pipeline.process_plate_event,
            frame,
            plate_bbox,
            persist_crop,
        )

    current_event_id = event_id or uuid4().hex

    failure_messages = {
        PlateProcessStatus.NO_VEHICLE_DETECTED: (
            "Зураг дээр тээврийн хэрэгсэл илрээгүй."
        ),
        PlateProcessStatus.NO_MATCHING_VEHICLE: (
            "Plate bbox-д тохирох тээврийн "
            "хэрэгсэл олдсонгүй."
        ),
        PlateProcessStatus.CLASSIFICATION_FAILED: (
            "Тээврийн хэрэгслийн ангиллын "
            "үр дүн үүссэнгүй."
        ),
    }

    if outcome.status != PlateProcessStatus.MATCHED:
        return PlateVehicleResponse(
            event_id=current_event_id,
            matched=False,
            plate_bbox=plate_bbox,
            reason_code=outcome.status.value,
            reason=failure_messages[outcome.status],
        )

    return PlateVehicleResponse(
        event_id=current_event_id,
        matched=True,
        plate_bbox=plate_bbox,
        vehicle_bbox=outcome.vehicle_bbox,
        match_score=outcome.match_score,
        result=outcome.result,
    )


@router.post(
    "/image",
    response_model=InferenceResponse,
)
async def recognize_image(
    request: Request,
    file: UploadFile = File(...),
):
    media = request.app.state.media
    pipeline = get_pipeline(request)

    upload_path = await media.save_upload(
        file=file,
        allowed_suffixes=IMAGE_SUFFIXES,
        max_bytes=settings.max_image_bytes,
    )

    try:
        try:
            frame = await run_in_threadpool(
                media.read_image,
                upload_path,
            )
        except ValueError as error:
            raise invalid_media(error) from error

        results = await run_in_threadpool(
            recognize_file_image,
            pipeline,
            frame,
        )

        return InferenceResponse(results=results)
    finally:
        media.remove_file(upload_path)


@router.post(
    "/video",
    response_model=InferenceResponse,
)
async def recognize_video(
    request: Request,
    file: UploadFile = File(...),
):
    media = request.app.state.media
    pipeline = get_pipeline(request)

    upload_path = await media.save_upload(
        file=file,
        allowed_suffixes=VIDEO_SUFFIXES,
        max_bytes=settings.max_video_bytes,
    )

    def process_video(path: Path):
        capture = cv2.VideoCapture(str(path))

        if not capture.isOpened():
            raise ValueError(
                "Бичлэгийг уншиж чадсангүй."
            )

        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = capture.get(cv2.CAP_PROP_FPS)

        if fps > 0 and frame_count > 0:
            duration_seconds = frame_count / fps
            if duration_seconds > settings.max_video_seconds:
                raise ValueError(
                    "Бичлэгийн үргэлжлэх хугацаа "
                    f"{settings.max_video_seconds:g} секундээс их байна."
                )

        state = TrackingState()
        results = []

        try:
            while True:
                success, frame = capture.read()

                if not success:
                    break

                _, frame_results = (
                    pipeline.process_tracked_frame(
                        frame,
                        state,
                    )
                )

                results.extend(enrich_results(frame, frame_results))
        finally:
            capture.release()

        return results

    try:
        try:
            results = await run_in_threadpool(
                process_video,
                upload_path,
            )
        except ValueError as error:
            raise invalid_media(error) from error

        return InferenceResponse(results=results)
    finally:
        media.remove_file(upload_path)


@router.post(
    "/vehicle",
    response_model=PlateVehicleResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_api_key)],
)
async def recognize_plate_vehicle_base64(
    request: Request,
    payload: PlateVehicleRequest,
):
    media = request.app.state.media
    pipeline = get_pipeline(request)

    try:
        frame = await run_in_threadpool(
            media.decode_base64_image,
            payload.image_base64,
            settings.max_image_bytes,
            settings.max_image_pixels,
        )
    except MediaTooLargeError as error:
        raise HTTPException(
            status_code=413,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    return await process_plate_frame(
        pipeline=pipeline,
        frame=frame,
        plate_bbox=payload.plate_bbox,
        event_id=payload.event_id,
        persist_crop=False,
    )


@router.post(
    "/vehicle/upload",
    response_model=PlateVehicleResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_api_key)],
)
async def recognize_plate_vehicle_upload(
    request: Request,
    file: UploadFile = File(...),
    event_id: str | None = Form(default=None),
    plate_x1: int = Form(...),
    plate_y1: int = Form(...),
    plate_x2: int = Form(...),
    plate_y2: int = Form(...),
):
    media = request.app.state.media
    pipeline = get_pipeline(request)

    try:
        plate_bbox = BoundingBox(
            x1=plate_x1,
            y1=plate_y1,
            x2=plate_x2,
            y2=plate_y2,
        )
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail="Bounding box coordinate буруу байна.",
        ) from error

    upload_path = await media.save_upload(
        file=file,
        allowed_suffixes=IMAGE_SUFFIXES,
        max_bytes=settings.max_image_bytes,
    )

    try:
        try:
            frame = await run_in_threadpool(
                media.read_image,
                upload_path,
            )
        except ValueError as error:
            raise invalid_media(error) from error

        return await process_plate_frame(
            pipeline=pipeline,
            frame=frame,
            plate_bbox=plate_bbox,
            event_id=event_id,
            persist_crop=False,
        )
    finally:
        media.remove_file(upload_path)


@router.post(
    "/video/sessions",
    response_model=VideoSessionResponse,
)
async def create_video_session(
    request: Request,
    file: UploadFile = File(...),
):
    media = request.app.state.media
    manager = get_video_manager(request)

    upload_path = await media.save_upload(
        file=file,
        allowed_suffixes=VIDEO_SUFFIXES,
        max_bytes=settings.max_video_bytes,
    )

    capture = cv2.VideoCapture(str(upload_path))
    try:
        if not capture.isOpened():
            raise invalid_media(
                ValueError("Бичлэгийг уншиж чадсангүй.")
            )

        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = capture.get(cv2.CAP_PROP_FPS)
        if fps > 0 and frame_count > 0:
            duration_seconds = frame_count / fps
            if duration_seconds > settings.max_video_seconds:
                raise invalid_media(
                    ValueError(
                        "Бичлэгийн үргэлжлэх хугацаа "
                        f"{settings.max_video_seconds:g} секундээс их байна."
                    )
                )
    except Exception:
        media.remove_file(upload_path)
        raise
    finally:
        capture.release()

    session = manager.create(upload_path)
    return VideoSessionResponse(session_id=session.session_id)


@router.get("/video/sessions/{session_id}/stream")
def video_session_stream(
    session_id: str,
    request: Request,
):
    manager = get_video_manager(request)

    try:
        stream = manager.stream(session_id)
        manager.get(session_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return StreamingResponse(
        stream,
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.websocket("/video/sessions/{session_id}/events")
async def video_session_events(
    websocket: WebSocket,
    session_id: str,
):
    await websocket.accept()
    manager = websocket.app.state.video_manager

    if manager is None:
        await websocket.close(code=1013)
        return

    sequence = 0
    previous_status = None

    try:
        while True:
            events = manager.events_after(session_id, sequence)

            for sequence, result in events:
                event = VideoRecognitionEvent(
                    session_id=session_id,
                    result=result,
                )
                await websocket.send_json(
                    event.model_dump(mode="json", by_alias=True)
                )

            status, error = manager.get_status(session_id)
            if status != previous_status:
                previous_status = status
                event = VideoStatusEvent(
                    session_id=session_id,
                    status=status,
                    error=error,
                )
                await websocket.send_json(
                    event.model_dump(mode="json", by_alias=True)
                )

            if status in {"completed", "error", "stopped"}:
                await websocket.close(code=1000)
                return

            await asyncio.sleep(0.05)
    except KeyError:
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass


@router.delete("/video/sessions/{session_id}", status_code=204)
def stop_video_session(
    session_id: str,
    request: Request,
):
    manager = get_video_manager(request)

    try:
        manager.delete(session_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error
