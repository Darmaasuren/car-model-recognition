import asyncio
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.schemas.recognition import InferenceResponse
from app.schemas.video import VideoRecognitionEvent, VideoSessionResponse, VideoStatusEvent
from app.services.recognition.client import RecognitionServiceError

router = APIRouter(prefix="/inference")
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv"}


@router.post("/video/sessions", response_model=VideoSessionResponse)
async def create_video_session(request: Request, file: UploadFile = File(...)):
    media = request.app.state.media
    path = await media.save_upload(file, VIDEO_SUFFIXES, settings.max_video_bytes)
    try:
        session_id = await run_in_threadpool(request.app.state.video_manager.create, path, request.scope['user'].id)
        return VideoSessionResponse(session_id=session_id)
    finally:
        media.remove_file(path)


@router.post("/video", response_model=InferenceResponse)
async def recognize_video(request: Request, file: UploadFile = File(...)):
    # Compatibility endpoint. UI uses asynchronous video sessions instead.
    session = await create_video_session(request, file)
    manager = request.app.state.video_manager
    sequence, results = 0, []
    try:
        while True:
            if await request.is_disconnected():
                raise HTTPException(499, "Client disconnected")
            events, status, error = await run_in_threadpool(manager.poll, session.session_id, sequence)
            for sequence, result in events:
                results.append(result)
            if len(results) > 1000:
                raise HTTPException(413, "Олон үр дүнтэй бичлэгт video session API ашиглана уу.")
            if status == "error":
                raise HTTPException(422, error or "Бичлэг боловсруулж чадсангүй.")
            if status in {"completed", "stopped"}:
                return InferenceResponse(results=results)
            await asyncio.sleep(.2)
    finally:
        await run_in_threadpool(manager.delete, session.session_id)


@router.get("/video/sessions/{session_id}/stream")
def video_session_stream(session_id: str, request: Request):
    manager = request.app.state.video_manager
    manager.authorize(session_id, request.scope['user'].id)
    stream, close = manager.stream(session_id)
    return StreamingResponse(stream, media_type="multipart/x-mixed-replace; boundary=frame", background=BackgroundTask(close))


@router.websocket("/video/sessions/{session_id}/events")
async def video_session_events(websocket: WebSocket, session_id: str):
    manager = websocket.app.state.video_manager
    try:
        await run_in_threadpool(manager.authorize, session_id, websocket.scope['user'].id)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    sequence, previous_status = 0, None
    try:
        while True:
            events, status, error = await run_in_threadpool(manager.poll, session_id, sequence)
            for sequence, result in events:
                await websocket.send_json(VideoRecognitionEvent(session_id=session_id, result=result).model_dump(mode="json", by_alias=True))
            if status != previous_status:
                previous_status = status
                await websocket.send_json(VideoStatusEvent(session_id=session_id, status=status, error=error).model_dump(mode="json", by_alias=True))
            if status in {"completed", "error", "stopped"}:
                await websocket.close(code=1000)
                return
            await asyncio.sleep(.2)
    except RecognitionServiceError as error:
        await websocket.send_json(VideoStatusEvent(session_id=session_id, status="error", error=str(error)).model_dump(mode="json", by_alias=True))
        await websocket.close(code=1013)
    except WebSocketDisconnect:
        pass


@router.delete("/video/sessions/{session_id}", status_code=204)
def stop_video_session(session_id: str, request: Request):
    manager = request.app.state.video_manager
    manager.authorize(session_id, request.scope['user'].id)
    manager.delete(session_id)
