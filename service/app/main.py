import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.error_handlers import register_error_handlers
from app.api.v1 import router as api_v1_router
from app.config import get_settings
from app.database import AsyncSessionFactory, close_database
from app.middleware import request_id_middleware
from app.middleware.upload_limit_middleware import UploadLimitMiddleware
from app.schemas.system_vo import HealthVO
from app.services.document_index_service import DocumentIndexService
from app.services.document_worker_service import DocumentWorkerService


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = DocumentWorkerService(
        AsyncSessionFactory, DocumentIndexService(settings.knowledge_data_dir)
    )
    task = asyncio.create_task(worker.run(), name="document-index-worker")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await close_database()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="基于 PostgreSQL 的 AI 项目协作助手。",
    lifespan=lifespan,
)
app.add_middleware(UploadLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)
app.middleware("http")(request_id_middleware)
register_error_handlers(app)

app.include_router(api_v1_router, prefix=settings.api_prefix)


@app.get("/", tags=["系统"], summary="服务入口")
async def root() -> dict[str, str]:
    return {
        "name": "DevPilot API",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }


@app.get(
    f"{settings.api_prefix}/health",
    response_model=HealthVO,
    tags=["系统"],
    summary="健康检查",
)
async def health_check() -> HealthVO:
    return HealthVO(
        status="ok",
        service="devpilot-api",
        timestamp=datetime.now(UTC),
        ai_mode=settings.ai_mode,
    )
