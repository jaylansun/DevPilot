import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.config import Settings
from app.database import Base
from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO
from app.models.user_do import UserDO, UserRole
from app.schemas.plan_vo import PlanProposalVO
from app.services.document_index_service import RetrievedChunk
from app.services.plan_agent_service import PlanAgentService, build_planning_model
from app.services.plan_service import PlanService
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langgraph.errors import GraphRecursionError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_plan_schema import proposal_data


def settings(**kwargs):
    values = {
        "database_url": "postgresql+psycopg://unused",
        "jwt_secret": "测试密钥",
        "ai_mode": "mock",
        "model_name": "",
        "llm_api_key": "",
        "llm_base_url": "",
        "rag_min_score": 0.5,
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({}, ("mock", "", "", "", 0.5)),
        ({"ai_mode": "live"}, ("live", "", "", "", 0.5)),
        (
            {
                "ai_mode": "live",
                "model_name": "fixture-model",
                "llm_api_key": "fixture-key",
                "llm_base_url": "https://fixture.invalid/v1",
                "rag_min_score": 0.8,
            },
            ("live", "fixture-model", "fixture-key", "https://fixture.invalid/v1", 0.8),
        ),
    ],
    ids=["defaults", "live_without_credentials", "explicit_configuration"],
)
def test_settings_ignore_external_live_configuration(monkeypatch, overrides, expected):
    """规划测试不继承部署模型配置，未配置场景始终保持空凭据。"""
    for name, value in {
        "AI_MODE": "live",
        "MODEL_NAME": "injected-model",
        "LLM_API_KEY": "injected-fake-key",
        "LLM_BASE_URL": "https://injected.invalid/v1",
        "RAG_MIN_SCORE": "0.9",
    }.items():
        monkeypatch.setenv(name, value)
    config = settings(**overrides)
    assert (
        config.ai_mode,
        config.model_name,
        config.llm_api_key.get_secret_value(),
        config.llm_base_url,
        config.rag_min_score,
    ) == expected
    assert config.database_url == "postgresql+psycopg://unused"
    assert config.jwt_secret.get_secret_value() == "测试密钥"


@pytest.mark.parametrize(
    "model,base_url,expected",
    [
        (
            "mimo-v2.5",
            "https://api.xiaomimimo.com/v1",
            {"thinking": {"type": "disabled"}},
        ),
        (
            "mimo-v2.5-pro",
            "https://api.xiaomimimo.com/v1/",
            {"thinking": {"type": "disabled"}},
        ),
        ("fixture-model", "https://fixture.invalid/v1", None),
        ("mimo-v2.5", "https://fixture.invalid/v1", None),
        ("fixture-model", "https://api.xiaomimimo.com/v1", None),
    ],
)
def test_planning_model_applies_mimo_tool_compatibility_only_to_official_models(
    monkeypatch, model, base_url, expected
):
    create_model = Mock()
    monkeypatch.setattr("app.services.plan_agent_service.ChatOpenAI", create_model)
    build_planning_model(settings(model_name=model, llm_base_url=base_url))
    assert create_model.call_args.kwargs["extra_body"] == expected
    assert create_model.call_args.kwargs["max_retries"] == 0
    assert create_model.call_args.kwargs["timeout"] == 25


@pytest.fixture
async def planning_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'plan.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, project, doc = uuid4(), uuid4(), uuid4()
    async with factory.begin() as session:
        session.add(
            UserDO(
                id=owner,
                username="规划测试",
                password_hash="测试",
                role=UserRole.MEMBER,
            )
        )
        await session.flush()
        session.add(
            ProjectDO(
                id=project, owner_id=owner, name="订单项目", description="实现下单"
            )
        )
        await session.flush()
        session.add(
            DocumentDO(
                id=doc,
                project_id=project,
                filename="订单.md",
                content="库存不足不能下单",
                content_hash="b" * 64,
                size_bytes=30,
                status=DocumentStatus.READY,
                chunk_count=1,
            )
        )
    index = Mock()
    index.search.return_value = [
        RetrievedChunk(doc, 0, "库存不足不能下单", "下单", 0.9)
    ]
    yield factory, owner, project, doc, index
    await engine.dispose()


async def test_mock_planning_reads_real_data_but_does_not_write(
    planning_context, monkeypatch
):
    factory, owner, project, _doc, index = planning_context
    monkeypatch.setattr(
        "app.services.plan_agent_service.ChatOpenAI",
        Mock(side_effect=AssertionError("演示模式不能初始化在线模型")),
    )
    service = PlanService(settings(), index, factory, PlanAgentService(settings()))
    async with factory.begin() as session:
        info = await service.info(session, owner, project)
        assert info.configured and info.ready_documents == 1
        first = await service.create(owner, project, "完善下单流程")
        second = await service.create(owner, project, "完善下单流程")
        count = await session.scalar(select(func.count(TaskDO.id)))
    assert count == 0
    assert not first.persisted and not second.persisted
    assert first.mode == "mock" and "固定模板" in first.proposal.summary
    assert len(first.proposal.tasks) == 3
    assert first.proposal.tasks[1].dependencies == ["T1"]
    assert {call.name for call in first.tool_calls} == {
        "search_documents",
        "read_task_board",
    }
    assert first.sources[0].text == "库存不足不能下单"


async def test_cross_project_denied_before_agent(planning_context):
    factory, _owner, project, _doc, index = planning_context
    agent = AsyncMock()
    service = PlanService(settings(), index, factory, agent)
    with pytest.raises(ApiError) as error:
        await service.create(uuid4(), project, "读取资料")
    assert error.value.status_code == 404
    agent.generate.assert_not_awaited()
    index.search.assert_not_called()


async def test_no_documents_or_configuration_short_circuits(planning_context):
    factory, owner, project, doc, index = planning_context
    agent = AsyncMock()
    service = PlanService(settings(ai_mode="live"), index, factory, agent)
    async with factory.begin() as session:
        with pytest.raises(ApiError) as error:
            await service.create(owner, project, "目标")
        assert error.value.code == "model_not_configured"
        (await session.get(DocumentDO, doc)).status = DocumentStatus.FAILED
    with pytest.raises(ApiError) as error:
        await service.create(owner, project, "目标")
    assert error.value.code == "planning_no_documents"
    agent.generate.assert_not_awaited()


@pytest.mark.parametrize(
    "case,expected",
    [
        ("skip_tools", "planning_missing_tools"),
        ("fake_source", "invalid_plan_sources"),
        ("duplicate", "duplicate_plan_task"),
        ("changed", "planning_context_changed"),
    ],
)
async def test_invalid_or_stale_plan_is_rejected(planning_context, case, expected):
    factory, owner, project, doc, index = planning_context
    if case == "duplicate":
        async with factory.begin() as session:
            session.add(TaskDO(project_id=project, title="实现下单校验"))

    async def generate(goal, context):
        if case != "skip_tools":
            await context.reader.search_documents(owner, project, goal)
            await context.reader.read_task_board(owner, project)
        data = proposal_data()
        if case == "fake_source":
            data["tasks"][0]["source_ids"] = [9]
        if case == "changed":
            async with factory.begin() as session:
                (await session.get(DocumentDO, doc)).status = DocumentStatus.DELETING
        return PlanProposalVO.model_validate(data)

    agent = AsyncMock()
    agent.generate.side_effect = generate
    service = PlanService(settings(), index, factory, agent)
    with pytest.raises(ApiError) as error:
        await service.create(owner, project, "目标")
    assert error.value.code == expected
    assert service._slots._value == 1


@pytest.mark.parametrize(
    "exception,code",
    [
        (TimeoutError(), "planning_timeout"),
        (RuntimeError("隐藏密钥及原文"), "planning_unavailable"),
        (
            ModelCallLimitExceededError(
                thread_count=5, run_count=5, thread_limit=None, run_limit=5
            ),
            "planning_limit",
        ),
        (
            ToolCallLimitExceededError(
                thread_count=7, run_count=7, thread_limit=None, run_limit=6
            ),
            "planning_limit",
        ),
        (GraphRecursionError("隐藏密钥及原文"), "planning_limit"),
    ],
)
async def test_safe_errors_and_slot_release(planning_context, exception, code, caplog):
    factory, owner, project, _doc, index = planning_context
    agent = AsyncMock()
    agent.generate.side_effect = exception
    service = PlanService(settings(), index, factory, agent)
    with pytest.raises(ApiError) as error:
        await service.create(owner, project, "目标")
    assert error.value.code == code
    assert "隐藏密钥" not in error.value.message + caplog.text
    if code == "planning_limit":
        assert type(exception).__name__ in caplog.text
        assert "限定步骤" in error.value.message
    assert service._slots._value == 1


async def test_cancel_and_busy_are_bounded(planning_context):
    factory, owner, project, _doc, index = planning_context
    started = asyncio.Event()

    async def wait(*_):
        started.set()
        await asyncio.Event().wait()

    agent = AsyncMock()
    agent.generate.side_effect = wait
    service = PlanService(settings(), index, factory, agent)
    task = asyncio.create_task(service.create(owner, project, "目标"))
    await asyncio.wait_for(started.wait(), timeout=3)
    with pytest.raises(ApiError) as error:
        await service.create(owner, project, "另一个目标")
    assert error.value.code == "planning_busy"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service._slots._value == 1


async def test_invalid_plan_error_explains_constraint_without_logging_model_input(
    planning_context, caplog
):
    factory, owner, project, _doc, index = planning_context
    data = proposal_data()
    data["tasks"][0]["priority"] = "private-model-output-never-log"
    try:
        PlanProposalVO.model_validate(data)
    except ValueError as failure:
        agent = AsyncMock()
        agent.generate.side_effect = failure
    service = PlanService(settings(), index, factory, agent)
    with pytest.raises(ApiError) as error:
        await service.create(owner, project, "目标")
    assert error.value.code == "invalid_plan"
    assert "优先级" in error.value.message and "整数" in error.value.message
    assert error.value.details[0]["field"] == "tasks.0.priority"
    assert "private-model-output-never-log" not in error.value.message + caplog.text
    assert service._slots._value == 1
