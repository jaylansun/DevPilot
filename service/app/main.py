import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, suppress
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
from app.services.approval_service import ApprovalService
from app.services.checkpoint_service import open_checkpointer
from app.services.document_index_service import DocumentIndexService
from app.services.document_worker_service import DocumentWorkerService
from app.services.plan_agent_service import PlanAgentService
from app.services.plan_service import PlanService
from app.services.rag_model_service import RagModelService
from app.services.rag_service import RagService
from app.services.workflow_model_service import WorkflowModelService
from app.services.workflow_service import WorkflowService

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    index_service = DocumentIndexService(settings.knowledge_data_dir)
    application.state.rag_service = RagService(
        settings, index_service, RagModelService(settings)
    )
    application.state.plan_service = PlanService(
        settings, index_service, AsyncSessionFactory, PlanAgentService(settings)
    )
    application.state.workflow_service = WorkflowService(
        settings, index_service, AsyncSessionFactory,
        WorkflowModelService(settings), RagModelService(settings),
    )
    async with AsyncExitStack() as stack:
        stack.push_async_callback(close_database)
        saver = await stack.enter_async_context(open_checkpointer(settings.database_url))
        application.state.approval_service = ApprovalService(
            AsyncSessionFactory, application.state.plan_service, saver
        )
        worker = DocumentWorkerService(AsyncSessionFactory, index_service)
        task = asyncio.create_task(worker.run(), name="document-index-worker")
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


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
