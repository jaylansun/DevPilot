"""故障穿过真实规划服务、持久 Graph 和事件流后，仍可恢复且不误写任务。"""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from app.schemas.approval_qo import ApprovalDecisionQO
from app.services.run_stream_service import StreamRunner
from openai import APITimeoutError
from test_approvals import actors as _actors
from test_approvals import pending, service_at, task_count
from test_planning_tools import planning_context as _planning_context

actors = _actors
planning_context = _planning_context


@pytest.mark.parametrize(
    "failure,code",
    [
        (
            APITimeoutError(request=httpx.Request("POST", "https://fixture.invalid")),
            "planning_timeout",
        ),
        (RuntimeError("private-provider-payload"), "planning_unavailable"),
    ],
)
async def test_model_failure_stream_keeps_original_conversation_recoverable(
    planning_context, actors, tmp_path, caplog, failure, code
):
    member, _, _ = actors
    path = tmp_path / "checkpoint.sqlite"
    async with service_at(planning_context, path) as service:
        conversation = await service.create(member, planning_context[2], "规划订单")
        service.planner.agent_service.generate = AsyncMock(side_effect=failure)
        runner = StreamRunner(
            lambda events: service.start(member, conversation.id, events=events),
            "approval",
            "failed-generation",
        )
        events = [json.loads(line) async for line in runner.stream()]
        assert events[-1]["type"] == "error"
        assert events[-1]["error"]["code"] == code
        assert sum(e["type"] in ("error", "final") for e in events) == 1
        assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
        assert "private-provider-payload" not in json.dumps(events) + caplog.text
        saved = await service.get(member, conversation.id)
        assert saved.status == "interrupted" and saved.approval is None
        assert await task_count(planning_context[0]) == 1
        assert service.planner._slots._value == 1
    # 重新建立服务和 Checkpointer，验证页面的“继续”确实可复用原会话。
    async with service_at(planning_context, path) as service:
        result = await service.start(member, conversation.id)
        assert result.status == "pending" and result.conversation_id == conversation.id
        assert await task_count(planning_context[0]) == 1


async def test_stream_timeout_after_decision_preserves_decision_and_releases_lock(
    planning_context, actors, tmp_path
):
    member, reviewer, _ = actors
    path = tmp_path / "checkpoint.sqlite"
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async with service_at(planning_context, path) as service:
        approval = await pending(service, planning_context, member)

        async def wait_for_storage(*_):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        service.persist_decision = wait_for_storage
        runner = StreamRunner(
            lambda events: service.decide(
                reviewer,
                approval.id,
                ApprovalDecisionQO(action="approve"),
                events=events,
            ),
            "approval",
            "approval-timeout",
            timeout=1,
        )
        events = [json.loads(line) async for line in runner.stream()]
        assert entered.is_set() and cancelled.is_set()
        assert events[-1]["error"]["code"] == "stream_timeout"
        assert sum(e["type"] in ("error", "final") for e in events) == 1
        saved = await service.get_approval(member, approval.id)
        assert saved.status == "processing" and saved.decision.action == "approve"
        assert await task_count(planning_context[0]) == 1
        async with service.execution_lock(approval.id):
            pass
    async with service_at(planning_context, path) as service:
        service.planner.create = AsyncMock(
            side_effect=AssertionError("已保存的方案不能重新生成")
        )
        body = ApprovalDecisionQO(action="approve")
        first = await service.decide(reviewer, approval.id, body)
        repeated = await service.decide(reviewer, approval.id, body)
        assert (
            first.status == "approved" and first.created_tasks == repeated.created_tasks
        )
        assert await task_count(planning_context[0]) == 1 + len(first.created_tasks)
