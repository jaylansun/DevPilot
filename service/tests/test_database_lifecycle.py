"""在真实 ASGI 发送边界验证提交时机，并用单连接池检测模型等待时的连接占用。"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from app import database
from app.api.dependencies import get_current_user
from app.api.error_handlers import register_error_handlers
from app.api.v1.project_controller import router as projects_router
from app.api.v1.rag_controller import get_rag_service
from app.api.v1.rag_controller import router as rag_router
from app.database import Base, get_session_factory
from app.middleware import request_id_middleware
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.user_do import UserDO, UserRole
from app.schemas.rag_vo import GroundedAnswerVO
from app.security import create_access_token
from app.services.document_index_service import RetrievedChunk
from app.services.rag_service import RagService
from fastapi import FastAPI
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_rag_service import settings


@pytest.fixture
async def lifecycle_context(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'lifecycle.db'}",
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.3,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user = UserDO(
        id=uuid4(), username="lifecycle", password_hash="unused", role=UserRole.MEMBER
    )
    async with factory.begin() as session:
        session.add(user)
    yield engine, factory, user
    await engine.dispose()


@pytest.mark.parametrize("fail_commit", [False, True])
async def test_write_commit_finishes_before_response(
    lifecycle_context, monkeypatch, fail_commit
):
    engine, factory, user = lifecycle_context
    monkeypatch.setattr(database, "AsyncSessionFactory", factory)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(projects_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    observations = []

    def commit(_connection):
        observations.append("commit")
        if fail_commit:
            raise RuntimeError("模拟数据库提交失败")

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps({"name": "事务验证"}).encode(),
            "more_body": False,
        }

    async def send(message):
        if message["type"] == "http.response.start":
            observations.append(message["status"])
            # 必须在发送响应这一刻，另一个事务已经能读到持久数据。
            async with factory() as session:
                count = await session.scalar(select(func.count(ProjectDO.id)))
                assert count == (0 if fail_commit else 1)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "root_path": "",
        "path": "/api/v1/projects",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    event.listen(engine.sync_engine, "commit", commit)
    try:
        if fail_commit:
            with pytest.raises(RuntimeError, match="模拟数据库提交失败"):
                await app(scope, receive, send)
        else:
            await app(scope, receive, send)
    finally:
        event.remove(engine.sync_engine, "commit", commit)
    assert observations == ["commit", 500 if fail_commit else 201]
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize("streaming", [False, True])
async def test_auth_and_rag_release_connections_while_model_waits(
    lifecycle_context, streaming
):
    engine, factory, user = lifecycle_context
    project, document = uuid4(), uuid4()
    async with factory.begin() as session:
        session.add(ProjectDO(id=project, owner_id=user.id, name="问答连接验证"))
        await session.flush()
        session.add(
            DocumentDO(
                id=document,
                project_id=project,
                filename="规则.md",
                content="不能重复下单",
                content_hash="a" * 64,
                size_bytes=18,
                chunk_count=1,
                status=DocumentStatus.READY,
            )
        )
    index, model = Mock(), AsyncMock()
    index.search.return_value = [
        RetrievedChunk(document, 0, "不能重复下单", "规则", 0.9)
    ]
    started, finish = asyncio.Event(), asyncio.Event()

    async def answer(*args, **kwargs):
        started.set()
        await finish.wait()
        return GroundedAnswerVO(
            answer="不能重复下单。[1]", source_ids=[1], insufficient_evidence=False
        )

    model.answer.side_effect = answer
    rag = RagService(settings(), index, model, factory)
    app = FastAPI()
    register_error_handlers(app)
    app.middleware("http")(request_id_middleware)
    app.include_router(rag_router, prefix="/api/v1")
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_rag_service] = lambda: rag
    path = f"/api/v1/projects/{project}/knowledge/questions" + (
        "/stream" if streaming else ""
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        request = asyncio.create_task(
            client.post(
                path,
                json={"question": "下单规则？"},
                headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 3)
            assert engine.pool.checkedout() == 0
            async with factory() as session:
                assert await session.scalar(select(func.count(UserDO.id))) == 1
            finish.set()
            response = await asyncio.wait_for(request, 3)
            assert response.status_code == 200
            if streaming:
                assert json.loads(response.text.splitlines()[-1])["type"] == "final"
            else:
                assert response.json()["status"] == "answered"
        finally:
            finish.set()
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
    assert engine.pool.checkedout() == 0
