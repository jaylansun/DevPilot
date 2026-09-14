import asyncio
import threading
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.user_do import UserDO, UserRole
from app.models.vector_cleanup_do import VectorCleanupDO
from app.services.document_service import (
    change_document_state,
    get_documents,
    upload_document,
)
from app.services.document_worker_service import DocumentWorkerService
from app.services.project_service import delete_project


@pytest.fixture
async def document_db(tmp_path):
    # 独立临时 SQLite 验证服务事务和恢复逻辑，不连接用户的开发数据库。
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner_id, project_id = uuid4(), uuid4()
    async with factory.begin() as session:
        session.add(
            UserDO(
                id=owner_id,
                username="文档测试",
                password_hash="测试",
                role=UserRole.MEMBER,
            )
        )
        await session.flush()
        session.add(
            ProjectDO(id=project_id, owner_id=owner_id, name="文档测试", description="")
        )
    yield factory, owner_id, project_id
    await engine.dispose()


async def add_document(factory, owner, project, content=b"test"):
    async with factory.begin() as session:
        return (await upload_document(session, owner, project, "需求.md", content)).id


async def test_owner_isolation_dedup_and_project_limit(document_db):
    factory, owner, project = document_db
    await add_document(factory, owner, project)
    async with factory.begin() as session:
        with pytest.raises(ApiError) as error:
            await get_documents(session, uuid4(), project)
        assert error.value.status_code == 404
    async with factory.begin() as session:
        with pytest.raises(ApiError) as error:
            await upload_document(session, owner, project, "copy.txt", b"test")
        assert error.value.code == "document_exists"
    for i in range(19):
        await add_document(factory, owner, project, str(i).encode())
    async with factory.begin() as session:
        with pytest.raises(ApiError) as error:
            await upload_document(session, owner, project, "extra.md", b"extra")
        assert error.value.code == "document_limit_reached"


async def test_worker_recovers_interrupted_index_and_deletes_vectors_first(document_db):
    factory, owner, project = document_db
    document = await add_document(factory, owner, project)
    index = Mock()
    index.index.return_value = 3
    worker = DocumentWorkerService(factory, index)
    async with factory.begin() as session:
        (await session.get(DocumentDO, document)).status = DocumentStatus.INDEXING
    await worker.recover()
    assert await worker.process_once()
    async with factory.begin() as session:
        doc = await session.get(DocumentDO, document)
        assert doc.status == DocumentStatus.READY
        assert doc.chunk_count == 3
        await change_document_state(session, owner, project, document, delete=True)
    assert await worker.process_once()
    index.delete_document.assert_called_once_with(project, document)
    async with factory.begin() as session:
        assert await session.get(DocumentDO, document) is None


async def test_failed_index_and_delete_are_visible_and_retryable(document_db):
    factory, owner, project = document_db
    document = await add_document(factory, owner, project)
    index = Mock()
    index.index.side_effect = RuntimeError("不得泄漏底层路径或凭据")
    worker = DocumentWorkerService(factory, index)
    await worker.process_once()
    async with factory.begin() as session:
        doc = await session.get(DocumentDO, document)
        assert doc.status == DocumentStatus.FAILED
        assert "凭据" not in doc.error_message
        await change_document_state(session, owner, project, document, delete=False)
    index.index.side_effect = None
    index.index.return_value = 2
    await worker.process_once()
    async with factory.begin() as session:
        await change_document_state(session, owner, project, document, delete=True)
    index.delete_document.side_effect = RuntimeError("磁盘不可用")
    await worker.process_once()
    async with factory.begin() as session:
        assert (
            await session.get(DocumentDO, document)
        ).status == DocumentStatus.DELETE_FAILED
        await change_document_state(session, owner, project, document, delete=False)
    index.delete_document.side_effect = None
    await worker.process_once()
    async with factory.begin() as session:
        assert await session.get(DocumentDO, document) is None


async def test_project_delete_queues_durable_cleanup_and_retries(document_db):
    factory, owner, project = document_db
    document = await add_document(factory, owner, project)
    async with factory.begin() as session:
        await delete_project(session, owner, project)
    async with factory.begin() as session:
        assert await session.get(DocumentDO, document) is None
        assert await session.get(VectorCleanupDO, project) is not None
    index = Mock()
    worker = DocumentWorkerService(factory, index)
    await worker.process_once()
    index.delete_project.assert_called_once_with(project)
    async with factory.begin() as session:
        assert await session.get(VectorCleanupDO, project) is None


@pytest.mark.parametrize("delete_whole_project", [False, True])
async def test_delete_during_index_never_resurrects_document(
    document_db, delete_whole_project
):
    factory, owner, project = document_db
    document = await add_document(factory, owner, project)
    started, released = threading.Event(), threading.Event()

    def slow_index(*_):
        started.set()
        assert released.wait(5)
        return 4

    index = Mock()
    index.index.side_effect = slow_index
    worker = DocumentWorkerService(factory, index)
    running = asyncio.create_task(worker.process_once())
    try:
        assert await asyncio.to_thread(started.wait, 5)
        async with factory.begin() as session:
            if delete_whole_project:
                await delete_project(session, owner, project)
            else:
                await change_document_state(
                    session, owner, project, document, delete=True
                )
    finally:
        released.set()
        await running
    async with factory.begin() as session:
        doc = await session.get(DocumentDO, document)
        assert (
            doc is None
            if delete_whole_project
            else doc.status == DocumentStatus.DELETING
        )
    await worker.process_once()
    if delete_whole_project:
        index.delete_project.assert_called_once_with(project)
    else:
        index.delete_document.assert_called_once_with(project, document)


async def test_project_cleanup_failure_is_retained_for_later_retry(document_db):
    factory, owner, project = document_db
    async with factory.begin() as session:
        await delete_project(session, owner, project)
    index = Mock()
    index.delete_project.side_effect = RuntimeError("暂时不可用")
    worker = DocumentWorkerService(factory, index)
    assert await worker.process_once()
    async with factory.begin() as session:
        assert await session.get(VectorCleanupDO, project) is not None
    # 失败后有退避时间，不应持续占用队列。
    assert not await worker.process_once()
