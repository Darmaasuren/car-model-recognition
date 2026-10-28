from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from recognition_service.api.security import require_api_key
from recognition_service.config import settings

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/video/sessions", status_code=201)
async def create_video(request: Request, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp4", ".mov", ".avi", ".mkv"}:
        await file.close()
        raise HTTPException(422, "Видео формат дэмжигдэхгүй байна.")
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    path = settings.runtime_dir / (uuid4().hex + suffix)
    # Reserve a bounded slot before writing the upload.
    try:
        session = request.app.state.sessions.create(path, path)
    except Exception:
        await file.close()
        raise
    size = 0
    try:
        with path.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_video_bytes:
                    raise HTTPException(413, "Видео хэмжээ хэтэрсэн.")
                target.write(chunk)
        if not size:
            raise HTTPException(422, "Хоосон видео байна.")
        return {"sessionId": session.session_id}
    except BaseException:
        request.app.state.sessions.delete(session.session_id)
        raise
    finally:
        await file.close()


@router.get("/video/sessions/{session_id}/events")
def video_events(session_id: str, request: Request, after: int = Query(0, ge=0)):
    return request.app.state.sessions.events_after(session_id, after)


@router.get("/video/sessions/{session_id}/stream")
def video_stream(session_id: str, request: Request):
    request.app.state.sessions.start(session_id)
    return StreamingResponse(request.app.state.sessions.stream(session_id), media_type="multipart/x-mixed-replace; boundary=frame")


@router.delete("/video/sessions/{session_id}", status_code=204)
def delete_video(session_id: str, request: Request):
    request.app.state.sessions.delete(session_id)


