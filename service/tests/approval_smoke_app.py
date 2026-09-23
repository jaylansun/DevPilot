"""浏览器集成验收专用应用：真实认证/API/PostgreSQL，离线模型与固定文档索引。"""

import os
from contextlib import asynccontextmanager
from unittest.mock import Mock
from uuid import UUID, uuid4

from app.api.error_handlers import register_error_handlers
from app.api.v1 import router
from app.config import get_settings
from app.database import get_db_session, get_session_factory
from app.middleware import request_id_middleware
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.user_do import UserDO, UserRole
from app.security import hash_password
from app.services.approval_service import ApprovalService
from app.services.checkpoint_service import open_checkpointer
from app.services.document_index_service import RetrievedChunk
from app.services.plan_agent_service import PlanAgentService
from app.services.plan_draft_service import PlanDraftService
from app.services.plan_service import PlanService
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

url = os.environ["TEST_APPROVAL_DATABASE_URL"]
assert make_url(url).database == "day12_test", "禁止连接业务数据库"
engine = create_async_engine(url)
factory = async_sessionmaker(engine, expire_on_commit=False)
project_id = UUID("22222222-2222-4222-8222-222222222222")
doc_id = UUID("33333333-3333-4333-8333-333333333333")


@asynccontextmanager
async def lifespan(app):
    async with factory.begin() as session:
        for name, role in [
            ("day12_member", UserRole.MEMBER),
            ("day12_reviewer", UserRole.REVIEWER),
        ]:
            user = await session.scalar(select(UserDO).where(UserDO.username == name))
            if user is None:
                user = UserDO(
                    id=uuid4(),
                    username=name,
                    password_hash=hash_password("day12-test-password"),
                    role=role,
                )
                session.add(user)
                await session.flush()
            if role == UserRole.MEMBER:
                member_id = user.id
        previous = await session.get(ProjectDO, project_id)
        if previous:
            await session.delete(previous)
            await session.flush()
        session.add(
            ProjectDO(
                id=project_id,
                owner_id=member_id,
                name="第十二天审批验收",
                description="订单流程",
            )
        )
        await session.flush()
        session.add(
            DocumentDO(
                id=doc_id,
                project_id=project_id,
                filename="订单规则.md",
                content="订单不得重复提交",
                content_hash="b" * 64,
                size_bytes=30,
                status=DocumentStatus.READY,
                chunk_count=1,
            )
        )
    index = Mock()
    index.search.return_value = [
        RetrievedChunk(doc_id, 0, "订单不得重复提交", "规则", 0.9)
    ]
    settings = get_settings()
    assert settings.ai_mode == "mock"
    app.state.plan_service = PlanService(
        settings, index, factory, PlanAgentService(settings)
    )
    async with open_checkpointer(url) as saver:
        app.state.approval_service = ApprovalService(
            factory, app.state.plan_service, saver
        )
        app.state.plan_draft_service = PlanDraftService(
            factory, app.state.plan_service, app.state.approval_service
        )
        try:
            yield
        finally:
            await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.middleware("http")(request_id_middleware)
register_error_handlers(app)
app.include_router(router, prefix="/api/v1")


async def database():
    async with factory.begin() as session:
        yield session


app.dependency_overrides[get_db_session] = database

app.dependency_overrides[get_session_factory] = lambda: factory
