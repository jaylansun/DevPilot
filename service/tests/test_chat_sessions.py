"""会话业务接口与真实 LangChain Agent/检查点的集成验证。"""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import func, select
from test_chat import ScriptedChatModel, finish, reply, service
from test_planning_tools import planning_context as _planning_context

from app.api.v1.chat_controller import get_chat_sessions
from app.errors import ApiError
from app.models.chat_do import ChatMessageDO, ChatSessionDO
from app.models.project_do import ProjectDO
from app.models.user_do import UserDO, UserRole
from app.schemas.chat_session import SessionMessageQO
from app.services.chat_session_service import ChatSessionService, now

planning_context = _planning_context


def body(question="你好", client_id=None):
    return SessionMessageQO(question=question, client_message_id=client_id or uuid4())


async def setup(context, *responses, **kwargs):
    chat = service(context, *(responses or [finish() for _ in range(30)]), **kwargs)
    sessions = ChatSessionService(context[0], chat)
    row = await sessions.create(context[1], context[2])
    return sessions, row.id


def humans(messages):
    return [m.content for m in messages if isinstance(m, HumanMessage)]


async def test_checkpoint_restart_replay_and_new_session_isolation(planning_context):
    factory, owner, project, *_ = planning_context
    sessions, sid = await setup(planning_context)
    request = body("这段会话的代号是蓝鲸")
    first = await sessions.answer(owner, project, sid, request)
    saver = sessions.chat.model_service.checkpointer
    restarted_chat = service(planning_context, finish(), finish(), saver=saver)
    restarted = ChatSessionService(factory, restarted_chat)
    assert await restarted.answer(owner, project, sid, request) == first
    restarted_chat.model_service.turn.assert_not_awaited()
    await restarted.answer(owner, project, sid, body("继续上一轮"))
    assert humans(restarted_chat.model_service.turn.await_args.args[0]) == [
        request.question,
        "继续上一轮",
    ]
    new = await restarted.create(owner, project)
    await restarted.answer(owner, project, new.id, body("新的问题"))
    assert humans(restarted_chat.model_service.turn.await_args.args[0]) == ["新的问题"]
    saved = await restarted.get(owner, project, sid)
    assert len(saved.messages) == 2 and all(
        m.status == "completed" for m in saved.messages
    )
    with pytest.raises(ApiError, match="相同消息"):
        await restarted.answer(
            owner, project, sid, body("换了问题", request.client_message_id)
        )


async def test_permissions_server_history_and_removed_memory_api(
    planning_context, api_app_factory
):
    factory, owner, project, *_ = planning_context
    sessions, sid = await setup(planning_context)
    other = uuid4()
    async with factory.begin() as db:
        db.add(ProjectDO(id=other, owner_id=owner, name="另一个项目"))
    for operation in (sessions.get, sessions.delete):
        for user, pid in [(owner, other), (uuid4(), project)]:
            with pytest.raises(ApiError):
                await operation(user, pid, sid)
    with pytest.raises(ApiError):
        await sessions.answer(owner, other, sid, body())
    app = api_app_factory(UserDO(id=owner, username="test", role=UserRole.MEMBER))
    app.dependency_overrides[get_chat_sessions] = lambda: sessions
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        prefix = f"/api/v1/projects/{project}/chat"
        for extra in [
            {"history": []},
            {"owner_id": str(owner)},
            {"project_id": str(project)},
        ]:
            response = await client.post(
                f"{prefix}/sessions/{sid}/messages",
                json={**body().model_dump(mode="json"), **extra},
            )
            assert response.status_code == 422
        assert (await client.get(prefix + "/memories")).status_code == 404
        assert (
            await client.patch(prefix + "/memory-settings", json={"auto_memory": True})
        ).status_code == 404
        response = await client.post(
            f"{prefix}/sessions/{sid}/messages/stream",
            json=body().model_dump(mode="json"),
        )
        assert response.status_code == 200
        assert json.loads(response.text.splitlines()[-1])["type"] == "final"
    assert (await sessions.get(owner, project, sid)).messages[0].status == "completed"


async def test_project_followup_requires_fresh_evidence_despite_saved_tool_history(
    planning_context,
):
    _, owner, project, _, _, index, _ = planning_context
    sessions, sid = await setup(
        planning_context,
        reply("search_documents", {"query": "订单规则"}),
        finish("订单不能重复。[1]", "project", [1]),
        finish("沿用上次资料。[1]", "project", [1]),
        reply("search_documents", {"query": "再次确认订单规则"}),
        finish("再次查询确认订单不能重复。[1]", "project", [1]),
    )
    await sessions.answer(owner, project, sid, body("订单规则是什么？"))
    followup = body("再确认一下")
    with pytest.raises(ApiError) as error:
        await sessions.answer(owner, project, sid, followup)
    assert error.value.code == "invalid_chat"
    assert index.search.call_count == 1
    result = await sessions.answer(owner, project, sid, followup)
    assert result.sources and index.search.call_count == 2
    assert len((await sessions.get(owner, project, sid)).messages) == 2


async def test_framework_summary_keeps_raw_records_and_stays_in_its_session(
    planning_context,
):
    _, owner, project, *_ = planning_context
    summary = AsyncMock(
        return_value=AIMessage(content="旧对话讨论了学习 Python 的目标")
    )
    sessions, sid = await setup(
        planning_context, summary_model=ScriptedChatModel(responder=summary)
    )
    for i in range(13):
        await sessions.answer(owner, project, sid, body(f"第 {i} 个问题"))
    assert summary.await_count > 0
    messages = sessions.chat.model_service.turn.await_args.args[0]
    assert any("旧对话讨论了学习 Python" in str(m.content) for m in messages)
    assert len(messages) < 40
    assert len((await sessions.get(owner, project, sid)).messages) == 13
    assert (await sessions.get(owner, project, sid, before=4)).messages[-1].seq == 3
    second = await sessions.create(owner, project)
    await sessions.answer(owner, project, second.id, body("新的开始"))
    messages = sessions.chat.model_service.turn.await_args.args[0]
    assert humans(messages) == ["新的开始"]
    assert not any("旧对话讨论了学习 Python" in str(m.content) for m in messages)


@pytest.mark.parametrize("prior", [False, True])
async def test_failed_checkpoint_never_enters_retry_context(planning_context, prior):
    factory, owner, project, *_ = planning_context
    sessions, sid = await setup(planning_context)
    if prior:
        await sessions.answer(owner, project, sid, body("已经成功的一轮"))
    request = body("本轮需要重试")
    sessions.chat.model_service.turn.side_effect = [
        finish("不该被记住的失败答案。[9]", "project", [9])
    ]
    with pytest.raises(ApiError):
        await sessions.answer(owner, project, sid, request)
    async with factory() as db:
        checkpoint_before = (await db.get(ChatSessionDO, sid)).checkpoint_id
    sessions.chat.model_service.turn.side_effect = [finish("重试成功")]
    await sessions.answer(owner, project, sid, request)
    messages = sessions.chat.model_service.turn.await_args.args[0]
    assert humans(messages) == (["已经成功的一轮"] if prior else []) + [
        request.question
    ]
    assert "不该被记住" not in str(messages)
    async with factory() as db:
        assert (await db.get(ChatSessionDO, sid)).checkpoint_id != checkpoint_before
        assert await db.scalar(select(func.count()).select_from(ChatMessageDO)) == (
            2 if prior else 1
        )


async def test_commit_failure_does_not_adopt_agent_checkpoint(
    planning_context, monkeypatch
):
    _, owner, project, *_ = planning_context
    sessions, sid = await setup(planning_context)
    request = body("保存失败需要重试")
    finish_original = sessions.finish
    monkeypatch.setattr(
        sessions, "finish", AsyncMock(side_effect=RuntimeError("commit unavailable"))
    )
    with pytest.raises(ApiError):
        await sessions.answer(owner, project, sid, request)
    monkeypatch.setattr(sessions, "finish", finish_original)
    await sessions.answer(owner, project, sid, request)
    assert humans(sessions.chat.model_service.turn.await_args.args[0]) == [
        request.question
    ]
    assert len((await sessions.get(owner, project, sid)).messages) == 1


async def test_cancel_busy_expiry_and_outdated_retry(planning_context):
    factory, owner, project, *_ = planning_context
    sessions, sid = await setup(planning_context)
    request = body()
    started = asyncio.Event()

    async def wait(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    sessions.chat.model_service.turn.side_effect = wait
    running = asyncio.create_task(sessions.answer(owner, project, sid, request))
    await asyncio.wait_for(started.wait(), 5)
    for operation in [
        sessions.answer(owner, project, sid, body("并发")),
        sessions.delete(owner, project, sid),
    ]:
        with pytest.raises(ApiError) as error:
            await operation
        assert error.value.code == "chat_session_busy"
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert (await sessions.get(owner, project, sid)).messages[0].status == "cancelled"
    sessions.chat.model_service.turn.side_effect = [finish()]
    await sessions.answer(owner, project, sid, request)
    abandoned = body("模拟中断")
    await sessions.start(owner, project, sid, abandoned)
    async with factory.begin() as db:
        row = await db.get(ChatSessionDO, sid)
        row.busy_until = now() - timedelta(seconds=1)
    assert (await sessions.get(owner, project, sid)).messages[-1].status == "failed"
    sessions.chat.model_service.turn.side_effect = [finish()]
    await sessions.answer(owner, project, sid, body("新一轮"))
    with pytest.raises(ApiError) as error:
        await sessions.answer(owner, project, sid, abandoned)
    assert error.value.code == "chat_retry_outdated"


async def test_delete_removes_checkpoints_and_missing_checkpoint_recovers(
    planning_context,
):
    factory, owner, project, *_ = planning_context
    sessions, sid = await setup(planning_context)
    await sessions.answer(owner, project, sid, body("需要保留的原始内容"))
    saver = sessions.chat.model_service.checkpointer
    await saver.adelete_thread(f"chat:{sid}")
    await sessions.answer(owner, project, sid, body("继续"))
    assert humans(sessions.chat.model_service.turn.await_args.args[0]) == [
        "需要保留的原始内容",
        "继续",
    ]
    await sessions.delete(owner, project, sid)
    assert (
        await saver.aget_tuple({"configurable": {"thread_id": f"chat:{sid}"}}) is None
    )
    with pytest.raises(ApiError):
        await sessions.get(owner, project, sid)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(ChatMessageDO)) == 0
