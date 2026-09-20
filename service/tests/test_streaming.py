import asyncio
import json
from pathlib import Path
from typing import get_args
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from app.api.v1.plan_controller import get_plan_service
from app.api.v1.rag_controller import get_rag_service
from app.api.v1.workflow_controller import get_workflow_service
from app.database import get_db_session
from app.errors import ApiError
from app.models.user_do import UserDO
from app.schemas.rag_vo import GroundedAnswerVO, RagAnswerVO, RagSourceVO
from app.schemas.stream_vo import StepName, stream_event_adapter
from app.services.plan_agent_service import PlanAgentService
from app.services.plan_service import PlanService
from app.services.rag_model_service import RagModelService
from app.services.rag_service import RagService, build_answer
from app.services.run_stream_service import emit, is_streaming, stream_events, trace
from fastapi.testclient import TestClient
from sqlalchemy import event as sql_event
from test_planning_tools import planning_context as _planning_context
from test_rag_model import configuration
from test_workflow import build_service
from test_workflow import run as run_workflow

planning_context = _planning_context


def answer():
    return RagAnswerVO(
        answer="回答", sources=[], status="insufficient_evidence", mode="mock"
    )


async def collect(run, kind="knowledge", request_id="stream-test"):
    return [json.loads(line) async for line in stream_events(run, kind, request_id)]


async def test_first_progress_arrives_before_completion_and_disconnect_cancels():
    gate, cancelled = asyncio.Event(), asyncio.Event()

    async def run():
        try:
            async with trace("answer_knowledge"):
                await gate.wait()
            return answer()
        finally:
            cancelled.set()

    iterator = stream_events(run, "knowledge", "cancel-test")
    first = json.loads(await asyncio.wait_for(anext(iterator), 1))
    assert first["status"] == "started" and not gate.is_set()
    await iterator.aclose()
    assert cancelled.is_set()
    assert not is_streaming()


async def test_backpressure_is_bounded_and_cancellation_unblocks_producer():
    count = 0
    stopped = asyncio.Event()

    async def run():
        nonlocal count
        try:
            for _ in range(1000):
                await emit("token", text="字")
                count += 1
            return answer()
        finally:
            stopped.set()

    iterator = stream_events(run, "knowledge", "slow-reader")
    await anext(iterator)
    await asyncio.sleep(0.02)
    assert count <= 33
    await asyncio.wait_for(iterator.aclose(), 1)
    assert stopped.is_set()


@pytest.mark.parametrize(
    "failure",
    [
        ApiError(409, "knowledge_changed", "资料已变化"),
        RuntimeError("private-key-and-document"),
    ],
)
async def test_partial_failure_has_one_safe_terminal_error(failure, caplog):
    async def run():
        await emit("token", text="临时回答")
        raise failure

    events = await collect(run)
    assert [value["type"] for value in events] == ["token", "error"]
    assert events[-1]["error"]["request_id"] == "stream-test"
    assert "private-key-and-document" not in json.dumps(events) + caplog.text


async def test_parallel_requests_do_not_share_events_or_sequence():
    async def run(text):
        await emit("token", text=text)
        await asyncio.sleep(0)
        return answer()

    first, second = await asyncio.gather(
        collect(lambda: run("甲"), request_id="a"),
        collect(lambda: run("乙"), request_id="b"),
    )
    assert first[0]["text"] == "甲" and second[0]["text"] == "乙"
    for events, request_id in [(first, "a"), (second, "b")]:
        assert [e["seq"] for e in events] == [1, 2]
        assert {e["request_id"] for e in events} == {request_id}


async def test_invalid_final_payload_does_not_leave_sequence_gap():
    async def run():
        await emit("token", text="临时内容")
        return answer()

    events = await collect(run, kind="planning")
    assert [e["seq"] for e in events] == [1, 2]
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]["code"] == "stream_unavailable"


@pytest.mark.parametrize(
    "kind,path,body,dependency",
    [
        (
            "knowledge",
            "knowledge/questions/stream",
            {"question": "规则？"},
            get_rag_service,
        ),
        (
            "planning",
            "planning/proposals/stream",
            {"goal": "规划任务"},
            get_plan_service,
        ),
        (
            "workflow",
            "assistant/runs/stream",
            {"message": "检查遗漏"},
            get_workflow_service,
        ),
    ],
)
async def test_stream_api_auth_contract_and_actual_readonly_services(
    planning_context,
    api_app_factory,
    reviewer_user,
    kind,
    path,
    body,
    dependency,
):
    factory, owner, project, _, _, index, engine = planning_context
    url = f"/api/v1/projects/{project}/{path}"
    for user, status in [(None, 401), (reviewer_user, 403)]:
        with TestClient(api_app_factory(user)) as client:
            assert client.post(url, json=body).status_code == status
    async with factory() as session:
        member = await session.get(UserDO, owner)
    app = api_app_factory(member)

    async def database():
        async with factory() as session:
            yield session

    config = configuration()
    service = {
        "knowledge": lambda: RagService(config, index, RagModelService(config)),
        "planning": lambda: PlanService(
            config, index, factory, PlanAgentService(config)
        ),
        "workflow": lambda: build_service(planning_context),
    }[kind]()
    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[dependency] = lambda: service
    statements = []

    def record(_conn, _cursor, statement, *_):
        statements.append(statement.strip().split()[0].upper())

    sql_event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            bad = await client.post(url, json={**body, "owner_id": str(owner)})
            assert bad.status_code == 422
            missing = await client.post(
                url.replace(str(project), str(uuid4())), json=body
            )
            assert (
                missing.status_code == 404
                and "application/json" in missing.headers["content-type"]
            )
            index.search.assert_not_called()
            response = await client.post(
                url, json=body, headers={"X-Request-ID": "api-stream-test"}
            )
    finally:
        sql_event.remove(engine.sync_engine, "before_cursor_execute", record)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["x-accel-buffering"] == "no"
    events = [
        stream_event_adapter.validate_json(line) for line in response.text.splitlines()
    ]
    assert events[-1].type == "final" and events[-1].kind == kind
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert {e.request_id for e in events} == {"api-stream-test"}
    assert statements and set(statements) == {"SELECT"}
    assert not any(e.type == "token" for e in events), "mock 不伪造模型增量"
    if kind == "planning":
        assert {e.name for e in events if e.type == "tool"} == {
            "search_documents",
            "read_task_board",
        }


async def test_real_graph_stream_respects_parallel_join(planning_context):
    service = build_service(planning_context)
    events = await collect(lambda: run_workflow(planning_context, service), "workflow")
    nodes = [(e.get("name"), e.get("status")) for e in events]
    report_index = nodes.index(("generate_report", "started"))
    assert nodes.index(("retrieve_documents", "completed")) < report_index
    assert nodes.index(("load_task_board", "completed")) < report_index
    assert nodes.index(("validate_result", "completed")) < len(events) - 1
    assert events[-1]["type"] == "final"


async def test_model_uses_actual_provider_chunks_before_final_validation(monkeypatch):
    from langchain_openai import ChatOpenAI

    gate = asyncio.Event()
    source = RagSourceVO(
        source_id=1,
        document_id=uuid4(),
        filename="规则.md",
        chunk_index=0,
        heading="",
        text="不能重复下单。",
    )

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            pieces = [
                '{"answer":"不能',
                '重复下单。[1]","source_ids":[1],"insufficient_evidence":false}',
            ]
            for i, piece in enumerate(pieces):
                if i:
                    await gate.wait()
                function = {"arguments": piece}
                if not i:
                    function["name"] = "GroundedAnswerVO"
                packet = {
                    "id": "fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call" if not i else None,
                                        "type": "function",
                                        "function": function,
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ],
                }
                yield (
                    "data: " + json.dumps(packet, ensure_ascii=False) + "\n\n"
                ).encode()
            yield b"data: [DONE]\n\n"

    def respond(request):
        payload = json.loads(request.content)
        assert payload["stream"] is True
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Body()
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(
            "langchain_openai.ChatOpenAI",
            lambda **kw: ChatOpenAI(**kw, http_async_client=client),
        )
        model = RagModelService(
            configuration(
                ai_mode="live",
                model_name="fixture",
                llm_api_key="fixture",
                llm_base_url="https://fixture.invalid/v1",
            )
        )

        async def run():
            result = await model.answer("可以重复下单吗？", [source])
            return build_answer(result, [source], "live")

        iterator = stream_events(run, "knowledge", "provider-stream")
        first = json.loads(await asyncio.wait_for(anext(iterator), 3))
        assert first["type"] == "token" and first["text"] == "不能"
        gate.set()
        rest = [json.loads(line) async for line in iterator]
    assert rest[-1]["type"] == "final"
    assert (
        first["text"] + "".join(e["text"] for e in rest if e["type"] == "token")
        == "不能重复下单。[1]"
    )


def test_shared_frontend_event_contract():
    contract = json.loads(
        (Path(__file__).parents[2] / "vue/src/types/stream.contract.json").read_text()
    )
    assert contract["version"] == 1
    assert contract["steps"] == list(get_args(StepName))
    for sample in contract["events"]:
        stream_event_adapter.validate_python(sample)
    assert {e["type"] for e in contract["events"]} == {
        "token",
        "node",
        "tool",
        "error",
        "final",
    }


async def test_invalid_citation_after_tokens_emits_error_and_releases_slot(
    planning_context,
):
    factory, owner, project, _, _, index, _ = planning_context

    async def bad_answer(*_):
        await emit("token", text="未校验内容。[999]")
        return GroundedAnswerVO(
            answer="未校验内容。[999]", source_ids=[999], insufficient_evidence=False
        )

    model = AsyncMock()
    model.answer.side_effect = bad_answer
    rag = RagService(configuration(), index, model)
    async with factory() as session:
        events = await collect(lambda: rag.answer(session, owner, project, "规则？"))
    assert any(e["type"] == "token" for e in events)
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]["code"] == "invalid_model_citations"
    assert not any(e["type"] == "final" for e in events)
    assert rag._slots._value == 1


async def test_asgi_disconnect_cancels_model_and_releases_service_slot(
    planning_context, api_app_factory
):
    factory, owner, project, _, _, index, _ = planning_context
    cancelled, disconnected = asyncio.Event(), asyncio.Event()

    async def wait_model(*_):
        try:
            await emit("token", text="正在生成")
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    model = AsyncMock()
    model.answer.side_effect = wait_model
    rag = RagService(configuration(), index, model)
    async with factory() as session:
        user = await session.get(UserDO, owner)
    app = api_app_factory(user)

    async def database():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[get_rag_service] = lambda: rag
    sent_body = False

    async def receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {
                "type": "http.request",
                "body": json.dumps({"question": "规则？"}).encode(),
                "more_body": False,
            }
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and b'"type":"token"' in message.get(
            "body", b""
        ):
            disconnected.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "root_path": "",
        "path": f"/api/v1/projects/{project}/knowledge/questions/stream",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), 3)
    assert cancelled.is_set() and disconnected.is_set()
    assert rag._slots._value == 1
