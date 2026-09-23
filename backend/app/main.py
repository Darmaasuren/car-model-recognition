from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.lifespan import lifespan
from app.api import auth, health, inference, live, service_comparison
from app.middleware.auth import AuthMiddleware


settings.crop_dir.mkdir(parents=True, exist_ok=True)


app = FastAPI(
    title="Vehicle Recognition API",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {
        "name": "Vehicle Recognition API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }

app.add_middleware(AuthMiddleware)
app.include_router(auth.router, prefix=settings.api_prefix)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/media/crops",
    StaticFiles(directory=settings.crop_dir),
    name="crops",
)

app.include_router(
    health.router,
    prefix=settings.api_prefix,
    tags=["health"],
)
app.include_router(
    inference.router,
    prefix=settings.api_prefix,
    tags=["inference"],
)
app.include_router(
    live.router,
    prefix=settings.api_prefix,
    tags=["live"],
)
app.include_router(service_comparison.router, prefix=settings.api_prefix)
