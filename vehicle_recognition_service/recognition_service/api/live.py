from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from recognition_service.api.security import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/live/cameras/{camera_id}/events")
def live_events(camera_id: str, request: Request, after: int = Query(0, ge=0)):
    sessions = request.app.state.sessions
    session = sessions.camera(camera_id)
    result = sessions.events_after(session.session_id, after)
    result["sessionId"] = session.session_id
    return result


@router.get("/live/cameras/{camera_id}/stream")
def live_stream(camera_id: str, request: Request):
    sessions = request.app.state.sessions
    session = sessions.camera(camera_id)
    sessions.start(session.session_id)
    return StreamingResponse(sessions.stream(session.session_id), media_type="multipart/x-mixed-replace; boundary=frame")


@router.delete("/live/cameras/{camera_id}", status_code=204)
def stop_camera(camera_id: str, request: Request):
    sessions = request.app.state.sessions
    session_id = sessions.cameras.get(camera_id)
    if session_id:
        sessions.delete(session_id)
