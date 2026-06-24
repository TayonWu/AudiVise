from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.tasks import router as tasks_router
from app.api.uploads import router as uploads_router
from app.api.videos import router as videos_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AudiVise API",
        version="0.1.0",
        description=(
            "AudiVise音视频语音内容理解平台，支持异步 ASR、"
            "时间戳证据问答和 Agent Trace。"
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["ETag"],
    )
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(uploads_router, prefix=settings.api_prefix)
    app.include_router(videos_router, prefix=settings.api_prefix)
    app.include_router(tasks_router, prefix=settings.api_prefix)
    app.include_router(chat_router, prefix=settings.api_prefix)
    return app


app = create_app()
