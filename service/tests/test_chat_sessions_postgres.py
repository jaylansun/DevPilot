"""仅连接独立测试库，验证 PostgreSQL 行锁与官方持久检查点。"""

import asyncio
import os
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_chat import finish, service
from test_chat_sessions import body, humans

from app.errors import ApiError
from app.models.chat_do import ChatMessageDO
from app.models.project_do import ProjectDO
from app.models.user_do import UserDO, UserRole
from app.services.chat_session_service import ChatSessionService
from app.services.checkpoint_service import open_checkpointer


@pytest.mark.skipif(
    not os.getenv("TEST_CHAT_DATABASE_URL"), reason="需要独立 PostgreSQL 聊天测试库"
)
async def test_postgres_concurrency_restart_checkpoints_and_deletion():
    url = os.environ["TEST_CHAT_DATABASE_URL"]
    engine = create_async_engine(url)
    assert engine.url.database == "chat_sessions_test", "仅允许隔离测试库"
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, project = uuid4(), uuid4()
    first = second = None
    try:
        async with factory.begin() as db:
            db.add(
                UserDO(
                    id=owner,
                    username=str(owner),
                    password_hash="test",
                    role=UserRole.MEMBER,
                )
            )
            await db.flush()
            db.add(ProjectDO(id=project, owner_id=owner, name="chat concurrency"))
        context = (factory, owner, project, None, None, Mock(), engine)
        request = body("只有这个会话知道的内容")
        async with open_checkpointer(url) as saver:
            chat = service(context, saver=saver)
            sessions = ChatSessionService(factory, chat)
            first, second = await asyncio.gather(
                sessions.create(owner, project), sessions.create(owner, project)
            )
            started, release = asyncio.Event(), asyncio.Event()

            async def respond(*args, **kwargs):
                assert engine.pool.checkedout() == 0
                started.set()
                await release.wait()
                return finish()

            chat.model_service.turn.side_effect = respond
            running = asyncio.create_task(
                sessions.answer(owner, project, first.id, request)
            )
            await asyncio.wait_for(started.wait(), 10)
            try:
                with pytest.raises(ApiError) as error:
                    await sessions.answer(owner, project, first.id, request)
                assert error.value.code == "chat_session_busy"
            finally:
                release.set()
            answer = await running
            assert await sessions.answer(owner, project, first.id, request) == answer
            assert chat.model_service.turn.await_count == 1
        # 关闭、重新打开真实数据库连接和 Agent，确认状态不依赖 Python 对象。
        async with open_checkpointer(url) as saver:
            chat = service(context, finish(), finish(), saver=saver)
            sessions = ChatSessionService(factory, chat)
            await sessions.answer(owner, project, first.id, body("继续"))
            assert humans(chat.model_service.turn.await_args.args[0]) == [
                request.question,
                "继续",
            ]
            await sessions.answer(owner, project, second.id, body("全新会话"))
            assert humans(chat.model_service.turn.await_args.args[0]) == ["全新会话"]
            await sessions.delete(owner, project, first.id)
            assert (
                await saver.aget_tuple(
                    {"configurable": {"thread_id": f"chat:{first.id}"}}
                )
                is None
            )
            assert (await sessions.get(owner, project, second.id)).messages[
                0
            ].question == "全新会话"
            await sessions.delete(owner, project, second.id)
            async with factory() as db:
                assert (
                    await db.scalar(select(func.count()).select_from(ChatMessageDO))
                    == 0
                )
    finally:
        async with factory.begin() as db:
            await db.execute(delete(UserDO).where(UserDO.id == owner))
        await engine.dispose()
