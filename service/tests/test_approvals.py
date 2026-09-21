import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from app.api.v1.approval_controller import get_approval_service
from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.task_do import TaskDO, TaskSource
from app.models.user_do import UserDO, UserRole
from app.schemas.approval_qo import ApprovalDecisionQO
from app.schemas.stream_vo import stream_event_adapter
from app.services.approval_service import ApprovalService
from app.services.plan_agent_service import PlanAgentService
from app.services.plan_service import PlanService
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy import func, select
from test_planning_tools import planning_context as _planning_context
from test_rag_model import configuration

planning_context = _planning_context


@pytest.fixture
async def actors(planning_context):
    factory, owner, *_ = planning_context
    async with factory.begin() as session:
        member = await session.get(UserDO, owner)
        reviewer = UserDO(
            id=uuid4(),
            username="审批测试",
            password_hash="测试",
            role=UserRole.REVIEWER,
        )
        other = UserDO(
            id=uuid4(), username="另一成员", password_hash="测试", role=UserRole.MEMBER
        )
        session.add_all([reviewer, other])
    return member, reviewer, other


@asynccontextmanager
async def service_at(context, path):
    factory, _, _, _, _, index, _ = context
    settings = configuration()
    planner = PlanService(settings, index, factory, PlanAgentService(settings))
    async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
        yield ApprovalService(factory, planner, saver)


async def pending(service, context, member):
    conversation = await service.create(member, context[2], "完善订单流程")
    approval = await service.start(member, conversation.id)
    assert approval.status == "pending" and approval.created_tasks == []
    return approval


async def task_count(factory):
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(TaskDO))


async def test_checkpoint_survives_restart_then_approve_exactly_once(
    planning_context, actors, tmp_path
):
    member, reviewer, _ = actors
    path = tmp_path / "checkpoint.sqlite"
    async with service_at(planning_context, path) as service:
        approval = await pending(service, planning_context, member)
        assert await task_count(planning_context[0]) == 1
        assert (await service.start(member, approval.conversation_id)).id == approval.id
    async with service_at(planning_context, path) as service:
        service.planner.create = AsyncMock(
            side_effect=AssertionError("恢复不能重新调用模型")
        )
        restored = await service.get(member, approval.conversation_id)
        assert restored.status == "pending" and restored.approval.plan == approval.plan
        body = ApprovalDecisionQO(action="approve")
        first, second = await asyncio.gather(
            service.decide(reviewer, approval.id, body),
            service.decide(reviewer, approval.id, body),
        )
        assert first.status == second.status == "approved"
        assert first.created_tasks == second.created_tasks
        assert await task_count(planning_context[0]) == 1 + len(
            approval.plan.proposal.tasks
        )
        service.planner.create.assert_not_awaited()
        async with planning_context[0]() as session:
            tasks = list(
                await session.scalars(
                    select(TaskDO).where(TaskDO.approval_id == approval.id)
                )
            )
        assert all(t.source == TaskSource.AI for t in tasks)
        ids = {str(t.id) for t in tasks}
        assert all(set(t.dependency_ids) <= ids for t in tasks)
        with pytest.raises(ApiError) as exc:
            await service.decide(
                reviewer, approval.id, ApprovalDecisionQO(action="reject")
            )
        assert exc.value.code == "approval_already_decided"


@pytest.mark.parametrize("action", ["reject", "edit_and_approve"])
async def test_reject_and_edit_before_approval(
    planning_context, actors, tmp_path, action
):
    member, reviewer, _ = actors
    async with service_at(planning_context, tmp_path / "checkpoint.sqlite") as service:
        approval = await pending(service, planning_context, member)
        proposal = approval.plan.proposal.model_copy(deep=True)
        proposal.tasks[0].title = "人工修改后的任务"
        result = await service.decide(
            reviewer,
            approval.id,
            ApprovalDecisionQO(
                action=action,
                proposal=proposal if action == "edit_and_approve" else None,
            ),
        )
        assert result.status == ("rejected" if action == "reject" else "approved")
        if action == "reject":
            assert await task_count(planning_context[0]) == 1
        else:
            assert result.created_tasks[0].title == "人工修改后的任务"
            assert result.plan.proposal.tasks[0].title != result.created_tasks[0].title


async def test_commit_before_checkpoint_failure_does_not_duplicate_tasks(
    planning_context, actors, tmp_path
):
    member, reviewer, _ = actors
    path = tmp_path / "checkpoint.sqlite"
    async with service_at(planning_context, path) as service:
        approval = await pending(service, planning_context, member)
        persist = service.persist_decision

        async def commit_then_fail(*args):
            await persist(*args)
            raise RuntimeError("模拟提交后进程中断")

        service.persist_decision = commit_then_fail
        with pytest.raises(RuntimeError):
            await service.decide(
                reviewer, approval.id, ApprovalDecisionQO(action="approve")
            )
    async with service_at(planning_context, path) as service:
        result = await service.decide(
            reviewer, approval.id, ApprovalDecisionQO(action="approve")
        )
        assert result.status == "approved"
        assert await task_count(planning_context[0]) == 1 + len(result.created_tasks)


async def test_cancel_after_decision_can_resume_without_regeneration(
    planning_context, actors, tmp_path
):
    member, reviewer, _ = actors
    path = tmp_path / "checkpoint.sqlite"
    reached = asyncio.Event()
    async with service_at(planning_context, path) as service:
        approval = await pending(service, planning_context, member)

        async def pause(*args):
            reached.set()
            await asyncio.Event().wait()

        service.persist_decision = pause
        task = asyncio.create_task(
            service.decide(reviewer, approval.id, ApprovalDecisionQO(action="approve"))
        )
        await asyncio.wait_for(reached.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await task_count(planning_context[0]) == 1
    async with service_at(planning_context, path) as service:
        service.planner.create = AsyncMock(side_effect=AssertionError("不能重新生成"))
        result = await service.decide(
            reviewer, approval.id, ApprovalDecisionQO(action="approve")
        )
        assert result.status == "approved"


async def test_changed_documents_and_invalid_edited_sources_are_rejected(
    planning_context, actors, tmp_path
):
    member, reviewer, _ = actors
    async with service_at(planning_context, tmp_path / "checkpoint.sqlite") as service:
        approval = await pending(service, planning_context, member)
        proposal = approval.plan.proposal.model_copy(deep=True)
        proposal.tasks[0].source_ids = [12]
        with pytest.raises(ApiError) as exc:
            await service.decide(
                reviewer,
                approval.id,
                ApprovalDecisionQO(action="edit_and_approve", proposal=proposal),
            )
        assert exc.value.code == "invalid_approval_sources"
        async with planning_context[0].begin() as session:
            (
                await session.get(DocumentDO, planning_context[3])
            ).status = DocumentStatus.DELETING
        with pytest.raises(ApiError) as exc:
            await service.decide(
                reviewer, approval.id, ApprovalDecisionQO(action="approve")
            )
        assert exc.value.code == "approval_documents_changed"
        assert (
            await service.decide(
                reviewer, approval.id, ApprovalDecisionQO(action="reject")
            )
        ).status == "rejected"
        assert await task_count(planning_context[0]) == 1


async def test_cancel_between_submission_and_interrupt_can_approve_in_one_request(
    planning_context, actors, tmp_path
):
    member, reviewer, _ = actors
    path = tmp_path / "checkpoint.sqlite"
    reached = asyncio.Event()

    class CancelAfterSubmission:
        async def emit(self, event_type, **data):
            if (
                data.get("name") == "submit_approval"
                and data.get("status") == "completed"
            ):
                reached.set()
                await asyncio.Event().wait()

    async with service_at(planning_context, path) as service:
        conversation = await service.create(member, planning_context[2], "完善订单流程")
        task = asyncio.create_task(
            service.start(member, conversation.id, events=CancelAfterSubmission())
        )
        await asyncio.wait_for(reached.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await service.get_approval(member, conversation.id)).status == "pending"
    async with service_at(planning_context, path) as service:
        service.planner.create = AsyncMock(side_effect=AssertionError("不能重新生成"))
        result = await service.decide(
            reviewer, conversation.id, ApprovalDecisionQO(action="approve")
        )
        assert result.status == "approved"
        assert await task_count(planning_context[0]) == 1 + len(result.created_tasks)
        service.planner.create.assert_not_awaited()


async def test_missing_checkpoint_does_not_record_an_unexecutable_decision(
    planning_context, actors, tmp_path
):
    member, reviewer, _ = actors
    async with service_at(planning_context, tmp_path / "original.sqlite") as service:
        approval = await pending(service, planning_context, member)
    async with service_at(planning_context, tmp_path / "missing.sqlite") as service:
        with pytest.raises(ApiError) as exc:
            await service.decide(
                reviewer, approval.id, ApprovalDecisionQO(action="approve")
            )
        assert exc.value.code == "approval_checkpoint_missing"
        unchanged = await service.get_approval(member, approval.id)
        assert unchanged.status == "pending" and unchanged.decision is None
        assert await task_count(planning_context[0]) == 1


async def test_approval_api_roles_scope_stream_and_validation(
    planning_context, actors, tmp_path, api_app_factory
):
    member, reviewer, other = actors
    async with service_at(planning_context, tmp_path / "checkpoint.sqlite") as service:

        def client_for(user):
            app = api_app_factory(user)
            app.dependency_overrides[get_approval_service] = lambda: service
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            )

        async with client_for(member) as client:
            created = await client.post(
                f"/api/v1/projects/{planning_context[2]}/conversations",
                json={"goal": "完善订单流程"},
            )
            assert created.status_code == 201
            id = created.json()["id"]
            response = await client.post(f"/api/v1/conversations/{id}/runs/stream")
            events = [
                stream_event_adapter.validate_json(line)
                for line in response.text.splitlines()
            ]
            assert events[-1].type == "final" and events[-1].kind == "approval"
            assert sum(e.type == "approval_required" for e in events) == 1
            assert [e.seq for e in events] == list(range(1, len(events) + 1))
            assert (
                await client.post(
                    f"/api/v1/approvals/{id}/decide/stream", json={"action": "approve"}
                )
            ).status_code == 403
        async with client_for(other) as client:
            assert (await client.get(f"/api/v1/conversations/{id}")).status_code == 404
            assert (await client.get(f"/api/v1/approvals/{id}")).status_code == 404
            assert (await client.get("/api/v1/approvals")).json()["total"] == 0
        async with client_for(reviewer) as client:
            assert (await client.get("/api/v1/approvals?status=pending")).json()[
                "total"
            ] == 1
            assert (
                await client.post(
                    f"/api/v1/approvals/{id}/decide/stream",
                    json={"action": "edit_and_approve"},
                )
            ).status_code == 422
            assert (
                await client.post(
                    f"/api/v1/approvals/{id}/decide/stream",
                    json={"action": "approve", "owner_id": str(member.id)},
                )
            ).status_code == 422
            response = await client.post(
                f"/api/v1/approvals/{id}/decide/stream", json={"action": "approve"}
            )
            assert '"status":"approved"' in response.text
        async with client_for(None) as client:
            assert (await client.get(f"/api/v1/approvals/{id}")).status_code == 401
