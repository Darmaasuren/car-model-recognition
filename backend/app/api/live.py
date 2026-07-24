import asyncio

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse


router = APIRouter(prefix="/live")


@router.get("/cameras/{camera_id}/stream")
def camera_stream(
    camera_id: str,
    request: Request,
):
    manager = request.app.state.live_manager

    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="Live manager бэлэн биш байна.",
        )

    try:
        stream = manager.stream(camera_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return StreamingResponse(
        stream,
        media_type=(
            "multipart/x-mixed-replace;"
            " boundary=frame"
        ),
    )


@router.websocket(
    "/cameras/{camera_id}/events"
)
async def camera_events(
    websocket: WebSocket,
    camera_id: str,
):
    await websocket.accept()

    manager = websocket.app.state.live_manager

    if manager is None:
        await websocket.close(code=1013)
        return

    sequence = 0

    try:
        while True:
            events = manager.events_after(
                camera_id,
                sequence,
            )

            for sequence, event in events:
                await websocket.send_json(
                    event.model_dump(
                        mode="json",
                        by_alias=True,
                    )
                )

            await asyncio.sleep(0.1)
    except KeyError:
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass