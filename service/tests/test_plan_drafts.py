import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from app.api.v1.plan_draft_controller import get_draft_service
from app.errors import ApiError
from app.models.approval_do import ConversationDO
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.plan_draft_do import PlanDraftDO
from app.models.task_do import TaskDO
from app.schemas.approval_qo import ApprovalDecisionQO
from app.schemas.plan_draft_qo import DraftSubmitQO, DraftUpdateQO
from app.schemas.plan_vo import PlanProposalVO
from app.services.plan_draft_service import PlanDraftService
from sqlalchemy import func, select
from test_approvals import actors as _actors
from test_approvals import service_at, task_count
from test_planning_tools import planning_context as _planning_context

actors = _actors
planning_context = _planning_context


def update_body(draft, title="核对并实现订单规则"):
    proposal = draft.plan.proposal.model_dump()
    proposal["summary"] = "成员编辑后的方案"
    proposal["tasks"][0]["title"] = title
    return DraftUpdateQO(
        version=draft.version, proposal=PlanProposalVO.model_validate(proposal)
    )


async def test_saved_edited_draft_submits_same_plan_once_across_restart(
    planning_context, actors, tmp_path
):
    factory, _, project, *_ = planning_context
    member, reviewer, _ = actors
    checkpoint = tmp_path / "checkpoint.sqlite"
    async with service_at(planning_context, checkpoint) as approvals:
        approvals.planner.create = AsyncMock(wraps=approvals.planner.create)
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        first = await drafts.generate(member, project, "完善订单流程")
        assert first.plan.persisted and first.version == 1 and first.status == "draft"
        saved = await drafts.update(member, project, first.id, update_body(first))
        assert saved.version == 2 and saved.plan.sources == first.plan.sources
        assert (await drafts.get(member, project, first.id)).plan == saved.plan
        result = await drafts.submit(
            member, project, saved.id, DraftSubmitQO(version=2)
        )
        assert result.plan == saved.plan and result.status == "pending"
        again = await drafts.submit(member, project, saved.id, DraftSubmitQO(version=2))
        assert again.id == result.id
        assert approvals.planner.create.await_count == 1
        assert await task_count(factory) == 1
        assert (await drafts.get(member, project, saved.id)).status == "submitted"
        with pytest.raises(ApiError) as error:
            await drafts.update(member, project, saved.id, update_body(saved))
        assert error.value.code == "draft_already_submitted"

    async with service_at(planning_context, checkpoint) as approvals:
        approvals.planner.create = AsyncMock(
            side_effect=AssertionError("送审不得重新生成")
        )
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        restored = await drafts.submit(
            member, project, saved.id, DraftSubmitQO(version=2)
        )
        assert restored.id == result.id and restored.plan == saved.plan
        approved = await approvals.decide(
            reviewer, result.id, ApprovalDecisionQO(action="approve")
        )
        retry = await drafts.submit(member, project, saved.id, DraftSubmitQO(version=2))
        assert retry.created_tasks == approved.created_tasks
        assert await task_count(factory) == 1 + len(saved.plan.proposal.tasks)
        async with factory() as session:
            assert await session.scalar(select(func.count(ConversationDO.id))) == 1
            tasks = list(
                await session.scalars(
                    select(TaskDO).where(TaskDO.approval_id == result.id)
                )
            )
        assert {task.title for task in tasks} == {
            task.title for task in saved.plan.proposal.tasks
        }
        approvals.planner.create.assert_not_awaited()


async def test_draft_version_and_source_guards(planning_context, actors, tmp_path):
    factory, _, project, *_ = planning_context
    member, reviewer, other = actors
    async with service_at(
        planning_context, tmp_path / "checkpoint.sqlite"
    ) as approvals:
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        first = await drafts.generate(member, project, "完善订单流程")
        for user, status in [(other, 404), (reviewer, 403)]:
            for operation in (
                drafts.get(user, project, first.id),
                drafts.update(user, project, first.id, update_body(first)),
                drafts.submit(user, project, first.id, DraftSubmitQO(version=1)),
            ):
                with pytest.raises(ApiError) as error:
                    await operation
                assert error.value.status_code == status
        with pytest.raises(ApiError) as error:
            await drafts.get(member, uuid4(), first.id)
        assert error.value.status_code == 404
        forged = update_body(first)
        forged.proposal.tasks[0].source_ids = [12]
        with pytest.raises(ApiError) as error:
            await drafts.update(member, project, first.id, forged)
        assert error.value.code == "invalid_draft_sources"
        saved = await drafts.update(member, project, first.id, update_body(first))
        for operation in (
            drafts.update(member, project, first.id, update_body(first, "不能覆盖")),
            drafts.submit(member, project, first.id, DraftSubmitQO(version=1)),
        ):
            with pytest.raises(ApiError) as error:
                await operation
            assert error.value.code == "draft_version_conflict"
        assert (await drafts.get(member, project, first.id)).plan == saved.plan
        page = await drafts.list(member, project, 0, 1)
        assert page.total == 1 and page.items[0].id == first.id
        assert (await drafts.list(member, project, 1, 1)).items == []


@pytest.mark.parametrize("change", ["delete", "hash", "duplicate"])
async def test_draft_submission_revalidates_documents_and_tasks(
    planning_context, actors, tmp_path, change
):
    factory, _, project, *_ = planning_context
    member, _, _ = actors
    async with service_at(
        planning_context, tmp_path / "checkpoint.sqlite"
    ) as approvals:
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        draft = await drafts.generate(member, project, "完善订单流程")
        async with factory.begin() as session:
            if change == "duplicate":
                session.add(
                    TaskDO(project_id=project, title=draft.plan.proposal.tasks[0].title)
                )
            else:
                document = await session.get(
                    DocumentDO, draft.plan.sources[0].document_id
                )
                if change == "delete":
                    document.status = DocumentStatus.DELETING
                else:
                    document.content_hash = "f" * 64
        with pytest.raises(ApiError) as error:
            await drafts.submit(member, project, draft.id, DraftSubmitQO(version=1))
        assert error.value.status_code == 409
        assert (await drafts.get(member, project, draft.id)).conversation_id is None
        async with factory() as session:
            assert await session.scalar(select(func.count(ConversationDO.id))) == 0


async def test_interrupted_submission_reuses_bound_conversation_without_model(
    planning_context, actors, tmp_path
):
    factory, _, project, *_ = planning_context
    member, _, _ = actors
    checkpoint = tmp_path / "checkpoint.sqlite"
    async with service_at(planning_context, checkpoint) as approvals:
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        draft = await drafts.generate(member, project, "完善订单流程")
        approvals.start = AsyncMock(side_effect=asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            await drafts.submit(member, project, draft.id, DraftSubmitQO(version=1))
        bound = await drafts.get(member, project, draft.id)
        assert bound.status == "submitted" and bound.conversation_id
    async with service_at(planning_context, checkpoint) as approvals:
        approvals.planner.create = AsyncMock(
            side_effect=AssertionError("恢复不得重新生成")
        )
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        approval = await drafts.submit(
            member, project, draft.id, DraftSubmitQO(version=1)
        )
        assert approval.conversation_id == bound.conversation_id
        assert approval.plan == draft.plan
        approvals.planner.create.assert_not_awaited()


async def test_parallel_submission_binds_only_one_conversation(
    planning_context, actors, tmp_path
):
    factory, _, project, *_ = planning_context
    member, _, _ = actors
    async with service_at(
        planning_context, tmp_path / "checkpoint.sqlite"
    ) as approvals:
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        draft = await drafts.generate(member, project, "完善订单流程")
        first, second = await asyncio.gather(
            *[
                drafts.submit(member, project, draft.id, DraftSubmitQO(version=1))
                for _ in range(2)
            ]
        )
        assert first.id == second.id
        async with factory() as session:
            assert await session.scalar(select(func.count(ConversationDO.id))) == 1


async def test_draft_api_stream_persistence_and_request_boundary(
    planning_context, actors, tmp_path, api_app_factory
):
    factory, _, project, *_ = planning_context
    member, _, other = actors
    async with service_at(
        planning_context, tmp_path / "checkpoint.sqlite"
    ) as approvals:
        approvals.planner.create = AsyncMock(wraps=approvals.planner.create)
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        app = api_app_factory(member)
        app.dependency_overrides[get_draft_service] = lambda: drafts
        base = f"/api/v1/projects/{project}/planning/drafts"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            assert (
                await client.post(
                    base + "/stream", json={"goal": "规划", "owner_id": str(other.id)}
                )
            ).status_code == 422
            response = await client.post(
                base + "/stream", json={"goal": "完善订单流程"}
            )
            events = [json.loads(line) for line in response.text.splitlines()]
            final = events[-1]
            assert final["type"] == "final" and final["kind"] == "draft"
            draft = final["result"]
            assert draft["plan"]["persisted"] is True
            url = base + "/" + draft["id"]
            assert (await client.get(url)).json() == draft
            assert (await client.get(base)).json()["total"] == 1
            proposal = draft["plan"]["proposal"]
            proposal["tasks"][0]["title"] = "客户端修改的标题"
            edited = await client.patch(url, json={"version": 1, "proposal": proposal})
            assert edited.status_code == 200 and edited.json()["version"] == 2
            assert (
                await client.patch(
                    url,
                    json={"version": 2, "proposal": proposal, "plan": draft["plan"]},
                )
            ).status_code == 422
            assert (
                await client.post(
                    url + "/submit/stream", json={"version": 2, "proposal": proposal}
                )
            ).status_code == 422
            response = await client.post(url + "/submit/stream", json={"version": 2})
            final = json.loads(response.text.splitlines()[-1])
            assert final["kind"] == "approval"
            assert final["result"]["plan"]["proposal"] == proposal
            assert approvals.planner.create.await_count == 1
        async with factory() as session:
            assert await session.scalar(select(func.count(PlanDraftDO.id))) == 1


@pytest.mark.parametrize("fail_commit", [False, True])
async def test_draft_stream_final_requires_successful_commit(
    planning_context, actors, tmp_path, fail_commit
):
    from app.services.run_stream_service import StreamRunner
    from sqlalchemy import event

    factory, _, project, *_, engine = planning_context
    member, _, _ = actors
    async with service_at(
        planning_context, tmp_path / "checkpoint.sqlite"
    ) as approvals:
        drafts = PlanDraftService(factory, approvals.planner, approvals)
        committed = []

        def commit(_connection):
            committed.append(True)
            if fail_commit:
                raise RuntimeError("模拟草案提交失败")

        event.listen(engine.sync_engine, "commit", commit)
        runner = StreamRunner(
            lambda events: drafts.generate(
                member, project, "完善订单流程", events=events
            ),
            "draft",
            "draft-commit-test",
        )
        try:
            events = []
            async for line in runner.stream():
                item = json.loads(line)
                events.append(item)
                if item["type"] == "final":
                    assert committed == [True]
                    async with factory() as session:
                        assert (
                            await session.scalar(select(func.count(PlanDraftDO.id)))
                            == 1
                        )
            assert events[-1]["type"] == ("error" if fail_commit else "final")
        finally:
            event.remove(engine.sync_engine, "commit", commit)
        assert committed == [True]
        async with factory() as session:
            assert await session.scalar(select(func.count(PlanDraftDO.id))) == (
                0 if fail_commit else 1
            )
