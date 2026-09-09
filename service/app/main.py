from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.database import close_database


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime
    ai_mode: str


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await close_database()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI 项目协作助手：第一天基础服务。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"name": "DevPilot API", "docs": "/docs", "health": f"{settings.api_prefix}/health"}


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="devpilot-api",
        timestamp=datetime.now(UTC),
        ai_mode=settings.ai_mode,
    )
