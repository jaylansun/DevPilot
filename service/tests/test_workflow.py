import asyncio
import threading
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.api.v1.workflow_controller import get_workflow_service
from app.database import get_db_session
from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO, TaskStatus
from app.models.user_do import UserDO
from app.schemas.rag_vo import GroundedAnswerVO
from app.schemas.workflow_qo import WorkflowRequestQO
from app.schemas.workflow_vo import GapReportVO, TaskLookupVO
from app.services.planning_read_service import PlanningReadService
from app.services.rag_model_service import RagModelService
from app.services.run_events import NOOP_EVENTS
from app.services.workflow_model_service import WorkflowModelService
from app.services.workflow_service import WorkflowService
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from pydantic import ValidationError
from sqlalchemy import event
from test_plan_agent import ScriptedPlanningModel
from test_plan_service import settings
from test_planning_tools import planning_context as _planning_context

planning_context = _planning_context


def report_data(task_id, *, missing=True):
    return {
        "summary": "在已读片段中，订单校验已安排；请核对其余需求。",
        "covered": [
            {
                "requirement": "订单校验",
                "explanation": "对应现有校验任务，仅表示已安排。",
                "source_ids": [1],
                "task_ids": [str(task_id)],
            }
        ],
        "missing": [
            {
                "requirement": "防止重复提交",
                "explanation": "可能没有对应任务，请核对任务说明。",
                "source_ids": [1],
            }
        ]
        if missing
        else [],
        "questions": [
            {
                "question": "重复订单如何识别？",
                "reason": "当前片段没有说明识别规则。",
                "source_ids": [1],
            }
        ],
        "reviewed_source_ids": [1],
        "insufficient_evidence": False,
    }


def build_service(context, *, live=False, model=None):
    factory, _owner, _project, _doc, _task, index, _engine = context
    config = (
        settings(
            ai_mode="live",
            model_name="fixture",
            llm_api_key="fixture",
            llm_base_url="https://fixture.invalid",
        )
        if live
        else settings()
    )
    return WorkflowService(
        config,
        index,
        factory,
        model or WorkflowModelService(config),
        RagModelService(config),
    )


async def run(
    context,
    service,
    message="对照需求检查遗漏",
    intent="auto",
    owner=None,
    *,
    events=NOOP_EVENTS,
    streaming=False,
):
    _factory, user, project, *_ = context
    return await service.run(
        owner or user,
        project,
        WorkflowRequestQO(message=message, intent=intent),
        events=events,
        streaming=streaming,
    )


@pytest.mark.parametrize(
    "message,intent,reads",
    [
        (
            "对照需求检查遗漏",
            "requirement_check",
            {"search_documents", "read_task_board"},
        ),
        ("文档中的订单规则是什么？", "knowledge_question", {"search_documents"}),
        ("有哪些进行中的任务？", "task_lookup", {"read_task_board"}),
        ("请删除全部任务", "clarify", set()),
    ],
)
async def test_real_graph_routes_and_select_only(
    planning_context, monkeypatch, message, intent, reads
):
    engine = planning_context[-1]
    statements = []

    def record(_conn, _cursor, statement, *_args):
        statements.append(statement.strip().split()[0].upper())

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    monkeypatch.setattr(
        "app.services.workflow_model_service.ChatOpenAI",
        Mock(side_effect=AssertionError("mock must be offline")),
    )
    try:
        result = await run(planning_context, build_service(planning_context), message)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    assert result.intent == intent
    assert {call.name for call in result.tool_calls} == reads
    assert result.persisted is False and result.scope.full_document_review is False
    assert statements and set(statements) == {"SELECT"}
    assert len(result.scope.tasks) == (1 if "read_task_board" in reads else 0)
    if intent == "requirement_check":
        assert result.status == "demo" and result.report is None
    if intent == "task_lookup":
        assert result.tasks[0].id == planning_context[4]
        assert result.tasks[0].status == TaskStatus.IN_PROGRESS


async def test_explicit_intent_overrides_classification(planning_context):
    service = build_service(planning_context)
    service.workflow.model.classify = AsyncMock(
        side_effect=AssertionError("explicit purpose must skip model routing")
    )
    result = await run(planning_context, service, "订单规则", "requirement_check")
    assert result.intent == "requirement_check"


async def test_parallel_nodes_finish_before_report(planning_context, monkeypatch):
    _factory, _owner, _project, _doc, task_id, index, _engine = planning_context
    started, board_finished = threading.Event(), threading.Event()
    original = PlanningReadService.read_task_board

    def search(*_args, **_kwargs):
        started.set()
        assert board_finished.wait(4), "看板读取不能被文档检索锁串行阻塞"
        return index.search.return_value

    index.search.side_effect = search

    async def read(self, *args):
        assert await asyncio.to_thread(started.wait, 3)
        value = await original(self, *args)
        board_finished.set()
        return value

    monkeypatch.setattr(PlanningReadService, "read_task_board", read)
    model = AsyncMock()

    async def report(message, sources, board):
        assert started.is_set() and board_finished.is_set()
        assert len(sources) == 1 and board["total"] == 1
        return GapReportVO.model_validate(report_data(task_id))

    model.report.side_effect = report
    result = await run(
        planning_context,
        build_service(planning_context, live=True, model=model),
        intent="requirement_check",
    )
    assert result.status == "reviewed"
    model.report.assert_awaited_once()


@pytest.mark.parametrize("missing", [True, False])
async def test_live_structured_report_with_and_without_gaps(planning_context, missing):
    task_id = planning_context[4]
    data = report_data(task_id, missing=missing)
    model = WorkflowModelService(settings(ai_mode="live"))
    scripted = ScriptedPlanningModel(
        replies=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "WorkflowIntentVO",
                        "args": {"intent": "requirement_check"},
                        "id": "intent",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "GapReportVO", "args": data, "id": "report"}],
            ),
        ]
    )
    model._model = scripted
    result = await run(
        planning_context, build_service(planning_context, live=True, model=model)
    )
    assert result.report.model_dump(mode="json") == data
    assert len(result.report.missing) == int(missing)
    assert scripted.calls == 2
    assert result.scope.retrieved_source_count == 1
    assert len(result.scope.ready_documents) == 1


@pytest.mark.parametrize("case", ["no_hits", "not_ready", "no_documents"])
async def test_insufficient_evidence_does_not_claim_no_gaps(planning_context, case):
    factory, _owner, _project, doc, _task, index, _engine = planning_context
    if case == "no_hits":
        index.search.return_value = []
    else:
        async with factory.begin() as session:
            document = await session.get(DocumentDO, doc)
            if case == "not_ready":
                document.status = DocumentStatus.INDEXING
            else:
                await session.delete(document)
    model = AsyncMock()
    result = await run(
        planning_context,
        build_service(planning_context, live=True, model=model),
        intent="requirement_check",
    )
    assert result.status == "insufficient_evidence" and result.report is None
    assert result.scope.board_read and not result.sources
    model.report.assert_not_awaited()
    if case != "no_hits":
        index.search.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [("source_ids", [4]), ("source_ids", [1, 1]), ("task_ids", [str(uuid4())])],
)
async def test_fabricated_evidence_and_task_ids_rejected(
    planning_context, field, value
):
    data = report_data(planning_context[4])
    data["covered"][0][field] = value
    model = AsyncMock()
    model.report.return_value = GapReportVO.model_validate(data)
    service = build_service(planning_context, live=True, model=model)
    with pytest.raises(ApiError) as failure:
        await run(planning_context, service, intent="requirement_check")
    assert failure.value.code in {"invalid_workflow_sources", "invalid_workflow_tasks"}
    assert service._slots._value == 1


async def test_fake_task_lookup_id_rejected(planning_context):
    model = AsyncMock()
    model.lookup.return_value = TaskLookupVO(summary="伪造任务", task_ids=[uuid4()])
    with pytest.raises(ApiError) as failure:
        await run(
            planning_context,
            build_service(planning_context, live=True, model=model),
            intent="task_lookup",
        )
    assert failure.value.code == "invalid_workflow_tasks"


@pytest.mark.parametrize("change", ["task", "new_task", "document", "project"])
async def test_changes_during_model_generation_rejected(planning_context, change):
    factory, _owner, project, doc, task_id, _index, _engine = planning_context

    async def report(*_args):
        async with factory.begin() as session:
            if change == "task":
                (await session.get(TaskDO, task_id)).status = TaskStatus.DONE
            elif change == "new_task":
                session.add(TaskDO(project_id=project, title="刚新增的任务"))
            elif change == "document":
                (await session.get(DocumentDO, doc)).status = DocumentStatus.DELETING
            else:
                (await session.get(ProjectDO, project)).description = "需求范围修改"
        return GapReportVO.model_validate(report_data(task_id))

    model = AsyncMock()
    model.report.side_effect = report
    with pytest.raises(ApiError) as failure:
        await run(
            planning_context,
            build_service(planning_context, live=True, model=model),
            intent="requirement_check",
        )
    assert (
        failure.value.code == "workflow_context_changed"
        and failure.value.status_code == 409
    )


async def test_parallel_read_cannot_establish_different_baselines(
    planning_context, monkeypatch
):
    factory, _owner, project, *_rest = planning_context
    original = PlanningReadService.read_task_board

    async def changed(self, *args):
        async with factory.begin() as session:
            session.add(TaskDO(project_id=project, title="并行期间新增"))
        return await original(self, *args)

    monkeypatch.setattr(PlanningReadService, "read_task_board", changed)
    with pytest.raises(ApiError) as failure:
        await run(planning_context, build_service(planning_context))
    assert failure.value.code == "workflow_context_changed"


async def test_cross_owner_denied_before_model_and_retrieval(planning_context):
    model = AsyncMock()
    with pytest.raises(ApiError) as failure:
        await run(
            planning_context,
            build_service(planning_context, model=model),
            owner=uuid4(),
        )
    assert failure.value.status_code == 404
    model.classify.assert_not_awaited()
    planning_context[5].search.assert_not_called()


async def test_empty_board_is_supported_and_large_board_is_rejected(planning_context):
    factory, _owner, project, _doc, task_id, _index, _engine = planning_context
    async with factory.begin() as session:
        await session.delete(await session.get(TaskDO, task_id))
    result = await run(planning_context, build_service(planning_context))
    assert result.scope.board_read and result.scope.tasks == []
    async with factory.begin() as session:
        session.add_all(
            TaskDO(project_id=project, title=f"任务{i}") for i in range(101)
        )
    with pytest.raises(ApiError) as failure:
        await run(planning_context, build_service(planning_context))
    assert failure.value.code == "workflow_board_too_large"


async def test_task_query_without_documents_and_no_match(planning_context):
    factory, _owner, _project, doc, *_rest = planning_context
    async with factory.begin() as session:
        (await session.get(DocumentDO, doc)).status = DocumentStatus.FAILED
    result = await run(
        planning_context, build_service(planning_context), "已完成的任务"
    )
    assert result.intent == "task_lookup" and result.tasks == []
    assert result.scope.board_read and not result.scope.document_search_performed


@pytest.mark.parametrize(
    "exc,code",
    [
        (TimeoutError(), "workflow_timeout"),
        (RuntimeError("密钥与原文不应显示"), "workflow_unavailable"),
    ],
)
async def test_errors_release_slot_without_sensitive_logs(
    planning_context, caplog, exc, code
):
    model = AsyncMock()
    model.classify.side_effect = exc
    service = build_service(planning_context, model=model)
    with pytest.raises(ApiError) as failure:
        await run(planning_context, service)
    assert failure.value.code == code and service._slots._value == 1
    assert "密钥与原文" not in failure.value.message + caplog.text


async def test_busy_and_cancel_are_bounded(planning_context):
    started = asyncio.Event()

    async def wait(*_args):
        started.set()
        await asyncio.Event().wait()

    model = AsyncMock()
    model.classify.side_effect = wait
    service = build_service(planning_context, model=model)
    task = asyncio.create_task(run(planning_context, service))
    await asyncio.wait_for(started.wait(), 3)
    try:
        with pytest.raises(ApiError) as failure:
            await run(planning_context, service)
        assert failure.value.code == "workflow_busy"
    finally:
        task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service._slots._value == 1


def test_api_requires_member(api_app_factory, reviewer_user):
    path = f"/api/v1/projects/{uuid4()}/assistant"
    for user, status in [(None, 401), (reviewer_user, 403)]:
        with TestClient(api_app_factory(user)) as client:
            assert client.get(path).status_code == status
            assert (
                client.post(path + "/runs", json={"message": "检查遗漏"}).status_code
                == status
            )


@pytest.mark.parametrize(
    "body",
    [
        {"message": " "},
        {"message": "字" * 2001},
        {"message": "需求", "intent": "write"},
        {"message": "需求", "owner_id": str(uuid4())},
        {"message": "需求", "approved": True},
        {"message": "需求", "project_id": str(uuid4())},
    ],
)
def test_api_rejects_identity_and_execution_fields(api_app_factory, member_user, body):
    app = api_app_factory(member_user)
    service = AsyncMock()
    app.dependency_overrides[get_workflow_service] = lambda: service
    with TestClient(app) as client:
        response = client.post(f"/api/v1/projects/{uuid4()}/assistant/runs", json=body)
    assert response.status_code == 422
    service.run.assert_not_awaited()


def test_schema_requires_evidence_for_each_claim_but_allows_no_suggestions():
    data = report_data(uuid4(), missing=False)
    data.update(covered=[], questions=[])
    assert GapReportVO.model_validate(data).missing == []
    data["missing"] = [
        {"requirement": "凭空添加", "explanation": "无依据", "source_ids": []}
    ]
    with pytest.raises(ValidationError):
        GapReportVO.model_validate(data)


async def test_model_declared_insufficient_evidence_is_preserved(planning_context):
    model = AsyncMock()
    data = report_data(planning_context[4], missing=False)
    data.update(
        covered=[], questions=[], insufficient_evidence=True, summary="片段不足以判断"
    )
    model.report.return_value = GapReportVO.model_validate(data)
    result = await run(
        planning_context,
        build_service(planning_context, live=True, model=model),
        intent="requirement_check",
    )
    assert result.status == "insufficient_evidence"


async def test_api_runs_real_graph_with_authenticated_project(
    planning_context, api_app_factory
):
    factory, owner, project, *_rest = planning_context
    async with factory() as session:
        user = await session.get(UserDO, owner)
    app = api_app_factory(user)
    service = build_service(planning_context)

    async def database():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[get_workflow_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        path = f"/api/v1/projects/{project}/assistant"
        info = await client.get(path)
        response = await client.post(
            path + "/runs", json={"message": "  对照需求检查遗漏  "}
        )
        forbidden = await client.post(
            f"/api/v1/projects/{uuid4()}/assistant/runs", json={"message": "任务"}
        )
    assert info.status_code == response.status_code == 200
    assert info.json()["task_count"] == 1
    assert response.json()["intent"] == "requirement_check"
    assert response.json()["persisted"] is False
    assert response.json()["scope"]["tasks"][0]["id"] == str(planning_context[4])
    assert forbidden.status_code == 404


@pytest.mark.parametrize("intent", ["knowledge_question", "task_lookup"])
async def test_live_routing_other_readonly_branches(planning_context, intent):
    model = WorkflowModelService(settings(ai_mode="live"))
    replies = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "WorkflowIntentVO",
                    "args": {"intent": intent},
                    "id": "classify",
                }
            ],
        )
    ]
    if intent == "task_lookup":
        replies.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "TaskLookupVO",
                        "args": {
                            "summary": "找到已有任务",
                            "task_ids": [str(planning_context[4])],
                        },
                        "id": "lookup",
                    }
                ],
            )
        )
    scripted = ScriptedPlanningModel(replies=replies)
    model._model = scripted
    service = build_service(planning_context, live=True, model=model)
    service.workflow.rag_model = AsyncMock()
    service.workflow.rag_model.answer.return_value = GroundedAnswerVO(
        answer="订单不能重复提交。[1]",
        source_ids=[1],
        insufficient_evidence=False,
    )
    result = await run(planning_context, service)
    assert result.intent == intent and result.status == "answered"
    if intent == "knowledge_question":
        assert result.answer.endswith("[1]") and not result.scope.board_read
        assert scripted.calls == 1
    else:
        assert result.tasks[0].id == planning_context[4]
        assert not result.scope.document_search_performed and scripted.calls == 2
        service.workflow.rag_model.answer.assert_not_awaited()


async def test_new_request_does_not_reuse_old_sources_or_snapshot(planning_context):
    factory, _owner, _project, _doc, task_id, index, _engine = planning_context
    service = build_service(planning_context)
    first = await run(planning_context, service)
    index.search.return_value = []
    async with factory.begin() as session:
        (await session.get(TaskDO, task_id)).title = "第二次请求看到的新标题"
    second = await run(planning_context, service)
    assert len(first.sources) == 1 and second.sources == []
    assert second.status == "insufficient_evidence"
    assert second.scope.tasks[0].title == "第二次请求看到的新标题"
    assert len(second.tool_calls) == 2


async def test_scope_exposes_truncated_task_details(planning_context):
    factory, _owner, _project, _doc, task_id, *_rest = planning_context
    async with factory.begin() as session:
        task = await session.get(TaskDO, task_id)
        task.description = "说明" * 300
        task.acceptance_criteria = "验收" * 300
    result = await run(planning_context, build_service(planning_context))
    assert result.scope.task_details_truncated
    task = result.scope.tasks[0]
    assert task.description_truncated and task.acceptance_criteria_truncated
    assert len(task.description) == len(task.acceptance_criteria) == 400


async def test_missing_live_configuration_fails_before_graph(planning_context):
    service = build_service(planning_context)
    service.settings = settings(ai_mode="live")
    service.workflow.model = AsyncMock()
    with pytest.raises(ApiError) as failure:
        await run(planning_context, service)
    assert failure.value.code == "model_not_configured"
    service.workflow.model.classify.assert_not_awaited()
