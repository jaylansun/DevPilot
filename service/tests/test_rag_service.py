import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.config import Settings
from app.database import Base
from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.user_do import UserDO, UserRole
from app.schemas.rag_vo import GroundedAnswerVO, RagSourceVO
from app.services.document_index_service import RetrievedChunk
from app.services.rag_service import RagService, build_answer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


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
    """服务测试固定模式和空凭据，显式覆盖仍按测试要求生效。"""
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


@pytest.fixture
async def rag_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rag.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, project, doc = uuid4(), uuid4(), uuid4()
    async with factory.begin() as session:
        session.add(
            UserDO(
                id=owner,
                username="问答测试",
                password_hash="测试",
                role=UserRole.MEMBER,
            )
        )
        await session.flush()
        session.add(
            ProjectDO(id=project, owner_id=owner, name="问答项目", description="")
        )
        await session.flush()
        session.add(
            DocumentDO(
                id=doc,
                project_id=project,
                filename="订单规则.md",
                content="不能重复提交订单。",
                content_hash="a" * 64,
                size_bytes=30,
                status=DocumentStatus.READY,
                chunk_count=1,
            )
        )
    index = Mock()
    index.search.return_value = [
        RetrievedChunk(doc, 0, "不能重复提交订单。", "订单规则", 0.9)
    ]
    model = AsyncMock()
    model.answer.return_value = GroundedAnswerVO(
        answer="不允许重复提交。[1]", source_ids=[1], insufficient_evidence=False
    )
    yield factory, owner, project, doc, index, model
    await engine.dispose()


async def test_rag_two_steps_and_auth_scope(rag_context):
    factory, owner, project, doc, index, model = rag_context
    rag = RagService(settings(), index, model)
    async with factory.begin() as session:
        with pytest.raises(ApiError) as error:
            await rag.answer(session, uuid4(), project, "订单规则？")
        assert error.value.status_code == 404
        index.search.assert_not_called()
        model.answer.assert_not_awaited()
        result = await rag.answer(session, owner, project, "订单规则？")
    assert result.sources[0].document_id == doc
    assert result.sources[0].filename == "订单规则.md"
    assert result.sources[0].text == "不能重复提交订单。"
    assert index.search.call_args.args[:2] == (project, [doc])
    assert model.answer.await_args.args[1] == result.sources


@pytest.mark.parametrize(
    "status",
    [
        DocumentStatus.QUEUED,
        DocumentStatus.INDEXING,
        DocumentStatus.FAILED,
        DocumentStatus.DELETING,
        DocumentStatus.DELETE_FAILED,
    ],
)
async def test_only_ready_documents_can_be_used(rag_context, status):
    factory, owner, project, doc, index, model = rag_context
    async with factory.begin() as session:
        (await session.get(DocumentDO, doc)).status = status
    async with factory.begin() as session:
        result = await RagService(settings(), index, model).answer(
            session, owner, project, "订单规则？"
        )
    assert result.status == "insufficient_evidence"
    index.search.assert_not_called()
    model.answer.assert_not_awaited()


async def test_empty_retrieval_does_not_call_model(rag_context):
    factory, owner, project, _doc, index, model = rag_context
    index.search.return_value = []
    async with factory.begin() as session:
        result = await RagService(settings(), index, model).answer(
            session, owner, project, "天气？"
        )
    assert result.status == "insufficient_evidence"
    assert result.sources == []
    model.answer.assert_not_awaited()


async def test_live_requires_explicit_configuration(rag_context):
    factory, owner, project, _doc, index, model = rag_context
    rag = RagService(settings(ai_mode="live"), index, model)
    async with factory.begin() as session:
        assert not (await rag.info(session, owner, project)).configured
        with pytest.raises(ApiError) as error:
            await rag.answer(session, owner, project, "订单规则？")
    assert error.value.code == "model_not_configured"
    index.search.assert_not_called()


@pytest.mark.parametrize(
    "exception,code",
    [
        (RuntimeError("秘密密钥不得泄露"), "rag_unavailable"),
        (TimeoutError(), "rag_timeout"),
    ],
)
async def test_errors_are_safe_and_release_capacity(rag_context, exception, code):
    factory, owner, project, _doc, index, model = rag_context
    model.answer.side_effect = exception
    rag = RagService(settings(), index, model)
    async with factory.begin() as session:
        with pytest.raises(ApiError) as error:
            await rag.answer(session, owner, project, "订单规则？")
    assert error.value.code == code
    assert "秘密" not in error.value.message
    assert rag._slots._value == 1


async def test_deleted_document_during_answer_is_not_returned(rag_context):
    factory, owner, project, doc, index, model = rag_context
    async with factory.begin() as session:

        async def answer(*_, **_options):
            (await session.get(DocumentDO, doc)).status = DocumentStatus.DELETING
            await session.flush()
            return GroundedAnswerVO(
                answer="不能重复下单。[1]", source_ids=[1], insufficient_evidence=False
            )

        model.answer.side_effect = answer
        with pytest.raises(ApiError) as error:
            await RagService(settings(), index, model).answer(
                session, owner, project, "订单规则？"
            )
        assert error.value.code == "knowledge_changed"


async def test_busy_worker_rejects_unbounded_queue(rag_context):
    factory, owner, project, _doc, index, model = rag_context
    rag = RagService(settings(), index, model)
    await rag._slots.acquire()
    try:
        async with factory.begin() as session:
            with pytest.raises(ApiError) as error:
                await rag.answer(session, owner, project, "订单规则？")
        assert error.value.code == "rag_busy"
        index.search.assert_not_called()
    finally:
        rag._slots.release()


async def test_cancelled_answer_releases_slot(rag_context):
    factory, owner, project, _doc, index, model = rag_context
    started = asyncio.Event()

    async def wait_forever(*_, **_options):
        started.set()
        await asyncio.Event().wait()

    model.answer.side_effect = wait_forever
    rag = RagService(settings(), index, model)
    async with factory.begin() as session:
        task = asyncio.create_task(rag.answer(session, owner, project, "订单规则？"))
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert rag._slots._value == 1


@pytest.mark.parametrize(
    "answer,ids",
    [("伪造来源[9]", [9]), ("没有引用", [1]), ("引用不一致[2]", [1]), ("无依据", [])],
)
def test_model_cannot_invent_citations(answer, ids):
    source = RagSourceVO(
        source_id=1,
        document_id=uuid4(),
        filename="真实文档.md",
        chunk_index=0,
        heading="",
        text="原文",
    )
    result = GroundedAnswerVO(
        answer=answer, source_ids=ids, insufficient_evidence=False
    )
    with pytest.raises(ApiError) as error:
        build_answer(result, [source], "live")
    assert error.value.code == "invalid_model_citations"


def test_model_abstention_clears_untrusted_answer_and_citations():
    result = GroundedAnswerVO(
        answer="未经证实的信息[99]", source_ids=[99], insufficient_evidence=True
    )
    answer = build_answer(result, [], "live")
    assert answer.status == "insufficient_evidence"
    assert answer.sources == []
    assert "未经证实" not in answer.answer
