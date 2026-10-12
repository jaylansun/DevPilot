"""助手消息、草案事务及旧数据升级的业务回归。"""

import asyncio
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select
from test_approvals import actors as _actors
from test_approvals import task_count
from test_chat import finish
from test_chat_unified import unified_chat
from test_plan_drafts import update_body
from test_planning_tools import planning_context as _planning_context

from app.errors import ApiError
from app.models.chat_do import ChatSessionDO
from app.models.plan_draft_do import PlanDraftDO
from app.schemas.approval_qo import ApprovalDecisionQO
from app.schemas.chat_session import SessionMessageQO
from app.schemas.plan_draft_qo import DraftSubmitQO
from app.services.approval_service import ApprovalService
from app.services.chat_session_service import ChatSessionService
from app.services.plan_draft_service import PlanDraftService

actors = _actors
planning_context = _planning_context


def request(question="补齐订单流程", *, intent="task_planning", identifier=None):
    return SessionMessageQO(
        question=question, intent=intent, client_message_id=identifier or uuid4()
    )


async def workspace(context):
    chat = unified_chat(context)
    approvals = ApprovalService(context[0], chat.planner, InMemorySaver())
    drafts = PlanDraftService(context[0], chat.planner, approvals)
    sessions = ChatSessionService(context[0], chat, drafts)
    row = await sessions.create(*context[1:3])
    return sessions, row.id, drafts, approvals


async def draft_count(factory):
    async with factory() as session:
        return await session.scalar(select(func.count(PlanDraftDO.id)))


async def test_saved_chat_plan_can_be_edited_submitted_and_approved_once(
    planning_context, actors
):
    owner, project = planning_context[1:3]
    member, reviewer, _ = actors
    sessions, sid, drafts, approvals = await workspace(planning_context)
    message = request()
    answer = await sessions.answer(owner, project, sid, message)
    artifact = answer.artifacts[0]
    assert artifact.type == "task_plan" and artifact.draft_id
    assert artifact.draft_version == 1 and artifact.result.persisted
    assert await draft_count(planning_context[0]) == 1
    assert await task_count(planning_context[0]) == 1
    restored = ChatSessionService(planning_context[0], sessions.chat, drafts)
    stored = (await restored.get(owner, project, sid)).messages[0]
    assert stored.intent == "task_planning"
    assert stored.answer.model_dump() == answer.model_dump()
    draft = await drafts.get(member, project, artifact.draft_id)
    assert draft.plan == artifact.result
    edited = await drafts.update(member, project, draft.id, update_body(draft))
    assert edited.version == 2
    approval = await drafts.submit(
        member, project, edited.id, DraftSubmitQO(version=edited.version)
    )
    assert approval.status == "pending" and approval.plan == edited.plan
    assert await task_count(planning_context[0]) == 1
    approved = await approvals.decide(
        reviewer, approval.id, ApprovalDecisionQO(action="approve")
    )
    await approvals.decide(reviewer, approval.id, ApprovalDecisionQO(action="approve"))
    assert await task_count(planning_context[0]) == 1 + len(approved.created_tasks)
    assert (
        await restored.answer(owner, project, sid, message)
    ).model_dump() == answer.model_dump()
    assert await draft_count(planning_context[0]) == 1
    sessions.chat.planner.create.assert_awaited_once()
    sessions.chat.model_service.turn.assert_not_awaited()


async def test_reusing_message_id_with_another_purpose_is_rejected(planning_context):
    owner, project = planning_context[1:3]
    sessions, sid, _drafts, _ = await workspace(planning_context)
    message = request()
    await sessions.answer(owner, project, sid, message)
    with pytest.raises(ApiError) as error:
        await sessions.answer(
            owner,
            project,
            sid,
            request(
                message.question,
                intent="requirement_check",
                identifier=message.client_message_id,
            ),
        )
    assert error.value.code == "message_id_conflict"
    assert (await sessions.get(owner, project, sid)).messages[
        0
    ].intent == "task_planning"
    assert await draft_count(planning_context[0]) == 1
    sessions.chat.workflow.run.assert_not_awaited()


async def test_draft_and_message_rollback_together_then_retry_has_one_saved_draft(
    planning_context, monkeypatch
):
    owner, project = planning_context[1:3]
    sessions, sid, drafts, _ = await workspace(planning_context)
    message = request()
    save = drafts.save_validated_plan

    async def fail_after_flush(*args, **kwargs):
        await save(*args, **kwargs)
        raise RuntimeError("模拟消息保存阶段失败")

    monkeypatch.setattr(drafts, "save_validated_plan", fail_after_flush)
    with pytest.raises(ApiError):
        await sessions.answer(owner, project, sid, message)
    assert await draft_count(planning_context[0]) == 0
    saved = (await sessions.get(owner, project, sid)).messages[0]
    assert saved.status == "failed" and saved.answer is None
    async with planning_context[0]() as db:
        assert (await db.get(ChatSessionDO, sid)).checkpoint_id is None
    with pytest.raises(ApiError) as error:
        await sessions.answer(
            owner,
            project,
            sid,
            request(
                message.question,
                intent="auto",
                identifier=message.client_message_id,
            ),
        )
    assert error.value.code == "message_id_conflict"
    monkeypatch.setattr(drafts, "save_validated_plan", save)
    result = await sessions.answer(owner, project, sid, message)
    assert result.artifacts[0].draft_id
    assert await draft_count(planning_context[0]) == 1
    assert len((await sessions.get(owner, project, sid)).messages) == 1
    assert (
        await sessions.answer(owner, project, sid, message)
    ).model_dump() == result.model_dump()
    assert sessions.chat.planner.create.await_count == 2


async def test_cancel_after_draft_flush_leaves_no_orphan_and_can_retry(
    planning_context, monkeypatch
):
    owner, project = planning_context[1:3]
    sessions, sid, drafts, _ = await workspace(planning_context)
    message = request()
    save = drafts.save_validated_plan
    flushed = asyncio.Event()

    async def pause_after_flush(*args, **kwargs):
        await save(*args, **kwargs)
        flushed.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(drafts, "save_validated_plan", pause_after_flush)
    running = asyncio.create_task(sessions.answer(owner, project, sid, message))
    try:
        await asyncio.wait_for(flushed.wait(), 10)
    finally:
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
    assert await draft_count(planning_context[0]) == 0
    saved = (await sessions.get(owner, project, sid)).messages[0]
    assert saved.status == "cancelled" and saved.answer is None
    monkeypatch.setattr(drafts, "save_validated_plan", save)
    await sessions.answer(owner, project, sid, message)
    assert await draft_count(planning_context[0]) == 1


async def test_report_snapshot_survives_session_restart_without_creating_draft(
    planning_context,
):
    owner, project = planning_context[1:3]
    sessions, sid, drafts, _ = await workspace(planning_context)
    message = request("检查重复订单的需求覆盖", intent="requirement_check")
    result = await sessions.answer(owner, project, sid, message)
    assert result.artifacts[0].result.report.covered[0].task_ids == [
        planning_context[4]
    ]
    restarted = ChatSessionService(planning_context[0], sessions.chat, drafts)
    stored = (await restarted.get(owner, project, sid)).messages[0]
    assert stored.answer.artifacts[0] == result.artifacts[0]
    assert stored.intent == "requirement_check"
    assert (
        await restarted.answer(owner, project, sid, message)
    ).model_dump() == result.model_dump()
    assert await draft_count(planning_context[0]) == 0
    sessions.chat.workflow.run.assert_awaited_once()
    sessions.chat.workflow.workflow.model.classify.assert_not_awaited()


@pytest.mark.parametrize("lost_checkpoint", [False, True])
@pytest.mark.parametrize("intent", ["task_planning", "requirement_check"])
async def test_followup_keeps_explicit_artifact_context_after_checkpoint_recovery(
    planning_context, intent, lost_checkpoint
):
    owner, project = planning_context[1:3]
    sessions, sid, _drafts, _ = await workspace(planning_context)
    first = await sessions.answer(owner, project, sid, request(intent=intent))
    if lost_checkpoint:
        await sessions.chat.model_service.delete_thread(f"chat:{sid}")
    sessions.chat.model_service.turn.side_effect = [finish("可以继续讨论上一轮结果。")]
    await sessions.answer(
        owner, project, sid, request("继续讨论这个结果", intent="auto")
    )
    messages = sessions.chat.model_service.turn.await_args.args[0]
    previous = [message.content for message in messages if message.type == "ai"]
    artifact = first.artifacts[0]
    detail = (
        artifact.result.proposal.tasks[0].title
        if artifact.type == "task_plan"
        else artifact.result.report.questions[0].question
    )
    assert any(detail in content for content in previous)
    assert [message.content for message in messages if message.type == "human"] == [
        "补齐订单流程",
        "继续讨论这个结果",
    ]


def test_migration_keeps_existing_messages_and_defaults_their_purpose():
    path = Path(__file__).parents[1] / "migrations/versions/0008_unified_assistant.py"
    spec = importlib.util.spec_from_file_location("assistant_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, question TEXT NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO chat_messages (id, question) VALUES (1, '原有问答')"
            )
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
            assert connection.exec_driver_sql(
                "SELECT question, intent FROM chat_messages"
            ).one() == ("原有问答", "auto")
            connection.exec_driver_sql(
                "UPDATE chat_messages SET intent = 'task_planning' WHERE id = 1"
            )
            with Operations.context(MigrationContext.configure(connection)):
                module.downgrade()
            assert (
                connection.exec_driver_sql(
                    "SELECT question FROM chat_messages"
                ).scalar_one()
                == "原有问答"
            )
            assert "intent" not in {
                column["name"]
                for column in sa.inspect(connection).get_columns("chat_messages")
            }
    finally:
        engine.dispose()
