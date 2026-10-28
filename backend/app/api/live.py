import asyncio
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.schemas.recognition import RecognitionEvent
from app.services.recognition.client import RecognitionServiceError

router = APIRouter(prefix="/live")


@router.get("/cameras/{camera_id}/stream")
def camera_stream(camera_id: str, request: Request):
    path = f"/live/cameras/{quote(camera_id, safe='')}/stream"
    stream, close = request.app.state.recognition_client.stream(path)
    return StreamingResponse(stream, media_type="multipart/x-mixed-replace; boundary=frame",
                             background=BackgroundTask(close))


@router.websocket("/cameras/{camera_id}/events")
async def camera_events(websocket: WebSocket, camera_id: str):
    await websocket.accept()
    results = websocket.app.state.recognition
    if results is None:
        await websocket.close(code=1013)
        return
    path = f"/live/cameras/{quote(camera_id, safe='')}/events"
    sequence = 0
    try:
        while True:
            events, status, error = await run_in_threadpool(results.tracking_events, path, sequence)
            if status in {"error", "stopped"}:
                raise RecognitionServiceError(error or "Камер зогссон байна.")
            for sequence, result in events:
                event = RecognitionEvent(camera_id=camera_id, result=result)
                await websocket.send_json(event.model_dump(mode="json", by_alias=True))
            await asyncio.sleep(.2)
    except (KeyError, HTTPException):
        await websocket.close(code=1008)
    except RecognitionServiceError as error:
        await websocket.close(code=1008 if error.status_code == 404 else 1013)
    except WebSocketDisconnect:
        pass
