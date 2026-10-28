import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from recognition_service.api import health, recognition, video, live
from recognition_service.config import settings
from recognition_service.lifespan import lifespan

app = FastAPI(title="Vehicle Recognition Service", version="1.0.0", lifespan=lifespan)
for router in (health.router, recognition.router, video.router, live.router):
    app.include_router(router, prefix=settings.api_prefix)


@app.exception_handler(Exception)
async def inference_error(request, error):
    logging.getLogger(__name__).error("Recognition request failed", exc_info=error)
    return JSONResponse({"detail": "Recognition processing failed"}, status_code=500)
