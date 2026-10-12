"""统一入口通过真实 LangChain 工具循环交付独立、可复核的业务工件。"""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, ValidationError
from sqlalchemy import delete
from test_chat import ScriptedChatModel, finish, reply
from test_chat import service as legacy_chat_service
from test_plan_service import settings
from test_planning_tools import planning_context as _planning_context
from test_streaming import RecordingPublisher
from test_workflow import build_service as workflow_service
from test_workflow import report_data

from app.errors import ApiError
from app.models.document_do import DocumentDO
from app.models.task_do import TaskDO
from app.schemas.chat_qo import ChatRequestQO
from app.schemas.chat_session import SessionMessageQO
from app.schemas.workflow_vo import GapReportVO
from app.services.chat_service import ChatService
from app.services.document_index_service import RetrievedChunk
from app.services.plan_agent_service import PlanAgentService
from app.services.plan_service import PlanService
from app.services.run_stream_service import StreamRunner

planning_context = _planning_context


class RecordingChatModel(ScriptedChatModel):
    bindings: list = Field(default_factory=list, exclude=True)

    def bind_tools(self, tools, **kwargs):
        self.bindings.append([convert_to_openai_tool(item) for item in tools])
        return super().bind_tools(tools, **kwargs)


def unified_chat(context, *responses, planner=True, workflow=True):
    """在线模式只用脚本模型；业务服务执行 SQLite 读取和真正的结果校验。"""
    factory, _owner, _project, _doc, task, index, _engine = context
    legacy = legacy_chat_service(context, *responses)
    legacy.model_service._model = RecordingChatModel(
        responder=legacy.model_service.turn
    )
    if planner is True:
        config = settings()
        planner = PlanService(config, index, factory, PlanAgentService(config))
        planner.create = AsyncMock(wraps=planner.create)
    if workflow is True:
        model = AsyncMock()
        model.report.return_value = GapReportVO.model_validate(report_data(task))
        workflow = workflow_service(context, live=True, model=model)
        workflow.run = AsyncMock(wraps=workflow.run)
    return ChatService(
        legacy.settings,
        index,
        factory,
        legacy.model_service,
        planner=planner or None,
        workflow=workflow or None,
    )


async def ask(chat, context, question="完善订单流程", intent="auto", **kwargs):
    return await chat.answer(
        context[1],
        context[2],
        ChatRequestQO(question=question, intent=intent),
        **kwargs,
    )


def artifact_finish(answer="已生成结果，请查看下方内容。"):
    return finish(answer, "project")


@pytest.mark.parametrize("schema", [ChatRequestQO, SessionMessageQO])
def test_request_intent_is_optional_but_rejects_other_execution_modes(schema):
    body = {"question": "订单"}
    if schema is SessionMessageQO:
        body["client_message_id"] = uuid4()
    assert schema(**body).intent == "auto"
    for intent in ("task_planning", "requirement_check"):
        assert schema(**body, intent=intent).intent == intent
    with pytest.raises(ValidationError):
        schema(**body, intent="execute_tasks")


async def test_general_chat_never_starts_planning_or_requirement_check(
    planning_context,
):
    chat = unified_chat(planning_context, finish("你好！"))
    result = await ask(chat, planning_context, "你好")
    assert result.basis == "general"
    assert result.sources == result.tasks == result.tool_calls == result.artifacts == []
    assert chat.model_service.turn.await_count == 1
    chat.planner.create.assert_not_awaited()
    chat.workflow.run.assert_not_awaited()
    planning_context[5].search.assert_not_called()


async def test_business_tool_schemas_only_accept_goal_and_scope(planning_context):
    chat = unified_chat(planning_context, finish())
    await ask(chat, planning_context, "你好")
    advertised = {
        item["function"]["name"]: item["function"]["parameters"]
        for item in chat.model_service._model.bindings[0]
    }
    for name, field in (
        ("generate_task_plan", "goal"),
        ("check_requirements", "scope"),
    ):
        schema = advertised[name]
        assert set(schema["properties"]) == {field}
        assert schema["required"] == [field]
        assert schema["properties"][field]["minLength"] == 1
        assert schema["properties"][field]["maxLength"] == 2000


async def test_auto_planning_delivers_real_proposal_and_authenticated_goal(
    planning_context,
):
    goal = "补充防重复订单的验收"
    events = RecordingPublisher()
    chat = unified_chat(
        planning_context,
        reply("generate_task_plan", {"goal": goal}),
        artifact_finish(),
    )
    result = await ask(chat, planning_context, events=events)
    assert result.basis == "project"
    assert result.sources == result.tasks == []
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.type == "task_plan" and artifact.goal == goal
    assert artifact.draft_id is artifact.draft_version is None
    assert artifact.result.proposal.tasks[0].source_ids == [1]
    assert artifact.result.sources[0].document_id == planning_context[3]
    assert artifact.result.board_task_count == 1
    assert artifact.result.persisted is False
    assert chat.planner.create.await_args.args[:3] == (*planning_context[1:3], goal)
    chat.workflow.run.assert_not_awaited()
    assert [call.name for call in result.tool_calls] == ["generate_task_plan"]
    assert any(
        item["type"] == "tool" and item["name"] == "generate_task_plan"
        for item in events.events
    )


async def test_auto_check_delivers_report_and_skips_workflow_classification(
    planning_context,
):
    scope = "核对重复订单的需求覆盖"
    chat = unified_chat(
        planning_context,
        reply("check_requirements", {"scope": scope}),
        artifact_finish(),
    )
    result = await ask(chat, planning_context)
    artifact = result.artifacts[0]
    assert artifact.type == "requirement_check"
    assert artifact.result.intent == "requirement_check"
    assert artifact.result.report.covered[0].task_ids == [planning_context[4]]
    assert artifact.result.report.reviewed_source_ids == [1]
    assert artifact.result.sources[0].document_id == planning_context[3]
    assert artifact.result.scope.board_read
    assert artifact.result.scope.full_document_review is False
    assert artifact.result.persisted is False
    args = chat.workflow.run.await_args.args
    assert args[:2] == planning_context[1:3]
    assert args[2].message == scope and args[2].intent == "requirement_check"
    chat.workflow.workflow.model.classify.assert_not_awaited()
    chat.workflow.workflow.model.report.assert_awaited_once()
    chat.planner.create.assert_not_awaited()
    assert [call.name for call in result.tool_calls] == ["check_requirements"]


async def test_auto_can_generate_both_artifacts_once(planning_context):
    calls = reply("generate_task_plan", {"goal": "实现订单幂等"})
    calls.tool_calls.extend(
        reply("check_requirements", {"scope": "订单需求覆盖"}).tool_calls
    )
    chat = unified_chat(planning_context, calls, artifact_finish())
    result = await ask(chat, planning_context)
    assert {item.type for item in result.artifacts} == {
        "task_plan",
        "requirement_check",
    }
    chat.planner.create.assert_awaited_once()
    chat.workflow.run.assert_awaited_once()
    assert result.sources == result.tasks == []


@pytest.mark.parametrize(
    "intent,artifact_type",
    [("task_planning", "task_plan"), ("requirement_check", "requirement_check")],
)
async def test_explicit_intent_executes_even_when_question_is_ambiguous(
    planning_context, intent, artifact_type
):
    chat = unified_chat(planning_context)
    chat.model_service.turn.side_effect = AssertionError(
        "explicit intent must not ask the chat model to select a tool"
    )
    result = await ask(chat, planning_context, "请看看", intent=intent)
    assert [item.type for item in result.artifacts] == [artifact_type]
    assert result.basis == "project" and result.sources == result.tasks == []
    chat.model_service.turn.assert_not_awaited()
    chat.workflow.workflow.model.classify.assert_not_awaited()
    if intent == "task_planning":
        assert chat.planner.create.await_args.args[2] == "请看看"
        chat.workflow.run.assert_not_awaited()
    else:
        assert chat.workflow.run.await_args.args[2].message == "请看看"
        chat.planner.create.assert_not_awaited()


@pytest.mark.parametrize("intent", ["auto", "task_planning", "requirement_check"])
async def test_project_authorization_precedes_all_business_execution(
    planning_context, intent
):
    chat = unified_chat(planning_context, finish())
    with pytest.raises(ApiError) as failure:
        await chat.answer(
            uuid4(),
            planning_context[2],
            ChatRequestQO(question="检查订单", intent=intent),
        )
    assert failure.value.status_code == 404
    chat.planner.create.assert_not_awaited()
    chat.workflow.run.assert_not_awaited()
    chat.model_service.turn.assert_not_awaited()


@pytest.mark.parametrize(
    "name,args",
    [
        ("generate_task_plan", {"goal": "订单", "project_id": str(uuid4())}),
        ("generate_task_plan", {"goal": "订单", "approved": True}),
        ("generate_task_plan", {"goal": " "}),
        ("generate_task_plan", {"goal": "字" * 2001}),
        ("check_requirements", {"scope": "订单", "owner_id": str(uuid4())}),
        ("check_requirements", {"scope": "订单", "intent": "task_lookup"}),
        ("check_requirements", {"scope": " "}),
        ("execute_tasks", {"goal": "订单"}),
    ],
)
async def test_business_tools_reject_scope_injection_and_invalid_arguments(
    planning_context, name, args
):
    chat = unified_chat(planning_context, reply(name, args))
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context)
    assert failure.value.code == "invalid_chat"
    chat.planner.create.assert_not_awaited()
    chat.workflow.run.assert_not_awaited()
    planning_context[5].search.assert_not_called()


@pytest.mark.parametrize(
    "name,args,method",
    [
        ("generate_task_plan", {"goal": "订单"}, "create"),
        ("check_requirements", {"scope": "订单"}, "run"),
    ],
)
@pytest.mark.parametrize("same_turn", [False, True])
async def test_each_heavy_tool_is_bounded_before_second_execution(
    planning_context, name, args, method, same_turn
):
    first, second = reply(name, args), reply(name, args)
    if same_turn:
        first.tool_calls.extend(second.tool_calls)
        responses = [first]
    else:
        responses = [first, second]
    chat = unified_chat(planning_context, *responses)
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context)
    assert failure.value.code in {"chat_tool_limit", "invalid_chat"}
    business = chat.planner if method == "create" else chat.workflow
    assert getattr(business, method).await_count <= 1
    if not same_turn:
        getattr(business, method).assert_awaited_once()


async def test_unconfigured_business_services_are_absent_from_advertised_tools(
    planning_context,
):
    chat = unified_chat(planning_context, finish(), planner=False, workflow=False)
    await ask(chat, planning_context, "你好")
    advertised = {
        item["function"]["name"]
        for item in chat.model_service._model.bindings[0]
    }
    assert "generate_task_plan" not in advertised
    assert "check_requirements" not in advertised
    chat.model_service.turn.side_effect = [
        reply("generate_task_plan", {"goal": "订单"})
    ]
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context)
    assert failure.value.code == "invalid_chat"


async def test_completion_cannot_forge_an_artifact_without_business_tool(
    planning_context,
):
    fake = finish("已生成任务草案。")
    fake.tool_calls[0]["args"]["artifacts"] = [
        {"type": "task_plan", "goal": "伪造草案", "result": {}}
    ]
    chat = unified_chat(planning_context, fake)
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context)
    assert failure.value.code == "invalid_chat"
    chat.planner.create.assert_not_awaited()
    chat.workflow.run.assert_not_awaited()


@pytest.mark.parametrize(
    "corruption,expected",
    [
        ("plan_source", "invalid_plan"),
        ("plan_persisted", "invalid_plan"),
        ("plan_missing_read", "invalid_plan"),
        ("plan_priority", "invalid_chat"),
        ("check_wrong_branch", "invalid_workflow_result"),
        ("check_source", "invalid_workflow_sources"),
        ("check_task", "invalid_workflow_tasks"),
    ],
)
async def test_adapter_result_is_revalidated_before_it_can_become_an_artifact(
    planning_context, corruption, expected
):
    chat = unified_chat(planning_context)
    intent = "task_planning" if corruption.startswith("plan_") else "requirement_check"
    original = chat.planner.create if intent == "task_planning" else chat.workflow.run

    async def corrupt(*args, **kwargs):
        result = await original(*args, **kwargs)
        if corruption in {"plan_source", "plan_priority"}:
            tasks = list(result.proposal.tasks)
            tasks[0] = tasks[0].model_copy(
                update={"source_ids": [2]}
                if corruption == "plan_source"
                else {"priority": "high"}
            )
            return result.model_copy(
                update={"proposal": result.proposal.model_copy(update={"tasks": tasks})}
            )
        if corruption == "plan_persisted":
            return result.model_copy(update={"persisted": True})
        if corruption == "plan_missing_read":
            return result.model_copy(update={"tool_calls": []})
        if corruption == "check_wrong_branch":
            return result.model_copy(update={"intent": "task_lookup"})
        covered = list(result.report.covered)
        covered[0] = covered[0].model_copy(
            update={"source_ids": [2]}
            if corruption == "check_source"
            else {"task_ids": [uuid4()]}
        )
        return result.model_copy(
            update={"report": result.report.model_copy(update={"covered": covered})}
        )

    if intent == "task_planning":
        chat.planner.create = AsyncMock(side_effect=corrupt)
    else:
        chat.workflow.run = AsyncMock(side_effect=corrupt)
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context, intent=intent)
    assert failure.value.code == expected
    chat.model_service.turn.assert_not_awaited()


async def test_check_artifact_cannot_include_a_document_outside_authenticated_project(
    planning_context,
):
    chat = unified_chat(planning_context)
    original = chat.workflow.run

    async def corrupt(*args, **kwargs):
        result = await original(*args, **kwargs)
        sources = list(result.sources)
        sources[0] = sources[0].model_copy(update={"document_id": uuid4()})
        return result.model_copy(update={"sources": sources})

    chat.workflow.run = AsyncMock(side_effect=corrupt)
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context, intent="requirement_check")
    assert failure.value.code in {
        "invalid_workflow_sources", "invalid_workflow_result", "chat_context_changed"
    }


@pytest.mark.parametrize("name", ["generate_task_plan", "check_requirements"])
async def test_artifact_source_numbers_cannot_be_used_as_chat_citations(
    planning_context, name
):
    args = {"goal" if name == "generate_task_plan" else "scope": "订单"}
    chat = unified_chat(
        planning_context,
        reply(name, args),
        finish("订单不允许重复提交。[1]", "project", [1]),
    )
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context)
    assert failure.value.code == "invalid_chat"


async def test_check_scope_tasks_cannot_be_claimed_as_chat_board_evidence(
    planning_context,
):
    chat = unified_chat(
        planning_context,
        reply("check_requirements", {"scope": "订单"}),
        finish("已有订单校验任务。", "project", tasks=[planning_context[4]]),
    )
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context)
    assert failure.value.code == "invalid_chat"


async def test_chat_and_plan_keep_distinct_sources_even_with_same_number(
    planning_context,
):
    _factory, _owner, _project, doc, _task, index, _engine = planning_context

    def search(_project, _documents, query, **_kwargs):
        if query == "正文订单规则":
            return [RetrievedChunk(doc, 0, "正文引用的订单规则", "正文", 0.9)]
        return [RetrievedChunk(doc, 1, "方案独立引用的验收规则", "方案", 0.9)]

    index.search.side_effect = search
    chat = unified_chat(
        planning_context,
        reply("search_documents", {"query": "正文订单规则"}),
        reply("generate_task_plan", {"goal": "补充验收"}),
        finish("正文引用的订单规则。[1] 已生成方案。", "project", [1]),
    )
    result = await ask(chat, planning_context)
    assert result.sources[0].source_id == 1
    assert result.sources[0].text == "正文引用的订单规则"
    plan = result.artifacts[0].result
    assert plan.sources[0].source_id == 1
    assert plan.sources[0].text == "方案独立引用的验收规则"
    assert plan.proposal.tasks[0].source_ids == [1]
    tool_messages = [
        message
        for message in chat.model_service.turn.await_args.args[0]
        if isinstance(message, ToolMessage)
        and message.name == "generate_task_plan"
    ]
    assert len(tool_messages) == 1
    # 工件引用只供工件渲染，聊天模型获得摘要，不能误把它当本轮正文证据。
    assert "方案独立引用的验收规则" not in tool_messages[0].content


@pytest.mark.parametrize(
    "intent,tool_name",
    [
        ("task_planning", "generate_task_plan"),
        ("requirement_check", "check_requirements"),
        ("auto", "generate_task_plan"),
        ("auto", "check_requirements"),
    ],
)
async def test_cancelling_business_execution_releases_chat_and_business_slots(
    planning_context, intent, tool_name
):
    tool_args = {"goal" if tool_name == "generate_task_plan" else "scope": "订单"}
    chat = unified_chat(
        planning_context, reply(tool_name, tool_args), artifact_finish()
    )
    started, stopped = asyncio.Event(), asyncio.Event()
    model = (
        chat.planner.agent_service
        if tool_name == "generate_task_plan"
        else chat.workflow.workflow.model
    )
    method = "generate" if tool_name == "generate_task_plan" else "report"
    original = getattr(model, method)

    async def block(*_args, **_kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    setattr(model, method, AsyncMock(side_effect=block))
    runner = StreamRunner(
        lambda events: ask(chat, planning_context, intent=intent, events=events),
        "chat",
        f"cancel-{intent}",
    )
    iterator = runner.stream()
    await anext(iterator)
    await asyncio.wait_for(started.wait(), 3)
    await iterator.aclose()
    assert stopped.is_set()
    setattr(model, method, original)
    if intent == "auto":
        chat.model_service.turn.side_effect = [
            reply(tool_name, tool_args), artifact_finish()
        ]
    result = await asyncio.wait_for(ask(chat, planning_context, intent=intent), 3)
    assert len(result.artifacts) == 1


@pytest.mark.parametrize("intent", ["auto", "task_planning"])
async def test_plan_without_matching_evidence_never_returns_a_success_artifact(
    planning_context, intent
):
    planning_context[5].search.return_value = []
    chat = unified_chat(
        planning_context, reply("generate_task_plan", {"goal": "订单"})
    )
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context, intent=intent)
    assert failure.value.code == "planning_no_evidence"


@pytest.mark.parametrize("intent", ["auto", "requirement_check"])
async def test_check_without_matching_evidence_preserves_insufficient_status(
    planning_context, intent
):
    planning_context[5].search.return_value = []
    chat = unified_chat(
        planning_context,
        reply("check_requirements", {"scope": "订单"}),
        artifact_finish(),
    )
    result = await ask(chat, planning_context, intent=intent)
    assert result.status == "insufficient_evidence"
    check = result.artifacts[0].result
    assert check.status == "insufficient_evidence"
    assert check.sources == [] and check.report is None
    chat.workflow.workflow.model.report.assert_not_awaited()


async def test_plan_without_ready_documents_preserves_business_error(
    planning_context,
):
    async with planning_context[0].begin() as session:
        await session.execute(delete(DocumentDO))
    chat = unified_chat(planning_context)
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context, intent="task_planning")
    assert failure.value.code == "planning_no_documents"
    chat.model_service.turn.assert_not_awaited()


@pytest.mark.parametrize("change", ["document", "task"])
@pytest.mark.parametrize("tool_name", ["generate_task_plan", "check_requirements"])
async def test_change_after_business_tool_before_final_answer_is_rejected(
    planning_context, change, tool_name
):
    factory, _owner, _project, doc, task, *_ = planning_context
    chat = unified_chat(planning_context)
    turn = 0

    async def respond(*_args, **_kwargs):
        nonlocal turn
        turn += 1
        if turn == 1:
            return reply(
                tool_name,
                {"goal" if tool_name == "generate_task_plan" else "scope": "订单"},
            )
        async with factory.begin() as session:
            if change == "document":
                (await session.get(DocumentDO, doc)).content_hash = "f" * 64
            else:
                (await session.get(TaskDO, task)).title = "生成期间改动的任务"
        return artifact_finish()

    chat.model_service.turn.side_effect = respond
    with pytest.raises(ApiError) as failure:
        await ask(chat, planning_context)
    assert failure.value.code == "chat_context_changed"
