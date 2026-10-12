"""真实 SDK 配合 HTTP 替身验证 MiMo 的工具循环、自然语言流与后端校验。"""

import asyncio
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import delete
from test_chat import ask, finish
from test_chat import service as legacy_service
from test_planning_tools import planning_context as _planning_context
from test_rag_model import configuration
from test_streaming import RecordingPublisher

from app.errors import ApiError
from app.models.document_do import DocumentDO
from app.models.task_do import TaskDO
from app.schemas.chat_qo import ChatRequestQO
from app.schemas.chat_session import SessionMessageQO
from app.services.chat_model_service import ChatModelService
from app.services.chat_service import ChatService
from app.services.chat_session_service import ChatSessionService
from app.services.model_compat import uses_mimo_auto_tools
from app.services.run_stream_service import StreamRunner

planning_context = _planning_context


def tool(name, args):
    return {
        "id": str(uuid4()),
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def wire_response(body, content=None, *, calls=None, finish=None):
    finish = finish or ("tool_calls" if calls else "stop")
    base = {"id": str(uuid4()), "created": 1, "model": "mimo-v2.5"}
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    if not body.get("stream"):
        return httpx.Response(
            200,
            json={
                **base,
                "object": "chat.completion",
                "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            },
        )
    deltas = [{"role": "assistant", "content": ""}]
    if content:
        deltas += [{"content": content[i : i + 3]} for i in range(0, len(content), 3)]
    if calls:
        deltas.append(
            {"tool_calls": [{"index": i, **call} for i, call in enumerate(calls)]}
        )
    frames = [{"index": 0, "finish_reason": None, "delta": delta} for delta in deltas]
    frames.append({"index": 0, "finish_reason": finish, "delta": {}})
    return httpx.Response(
        200,
        headers={"Content-Type": "text/event-stream"},
        content="".join(
            "data: "
            + json.dumps(
                {**base, "object": "chat.completion.chunk", "choices": [frame]}
            )
            + "\n\n"
            for frame in frames
        )
        + "data: [DONE]\n\n",
    )


@asynccontextmanager
async def mimo_chat(context, monkeypatch, respond, *, saver=None):
    from langchain_openai import ChatOpenAI

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(
            "langchain_openai.ChatOpenAI",
            lambda **kwargs: ChatOpenAI(**kwargs, http_async_client=client),
        )
        settings = configuration(
            ai_mode="live",
            model_name="mimo-v2.5",
            llm_api_key="synthetic-test-key",
            llm_base_url="https://api.xiaomimimo.com/v1",
        )
        model = ChatModelService(
            settings, saver if saver is not None else InMemorySaver()
        )
        yield ChatService(settings, context[5], context[0], model)


@pytest.mark.parametrize("streaming", [False, True])
async def test_plain_answer_needs_one_model_call_and_streams_text(
    planning_context, monkeypatch, streaming
):
    requests = []
    answer = "珠海市位于广东省。"

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["tool_choice"] == "auto"
        assert {t["function"]["name"] for t in body["tools"]} == {
            "search_documents",
            "read_task_board",
        }
        assert body["thinking"] == {"type": "disabled"}
        assert "response_format" not in body
        return wire_response(body, answer)

    events = RecordingPublisher()
    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        result = await chat.answer(
            planning_context[1],
            planning_context[2],
            ChatRequestQO(question="珠海市"),
            events=events,
            streaming=streaming,
        )
    assert result.answer == answer
    assert result.basis == "general" and result.status == "answered"
    assert result.sources == result.tasks == result.tool_calls == []
    assert len(requests) == 1
    planning_context[5].search.assert_not_called()
    tokens = [e["text"] for e in events.events if e["type"] == "token"]
    if streaming:
        assert len(tokens) > 1 and "".join(tokens) == answer
    else:
        assert not tokens


@pytest.mark.parametrize("invalid", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
async def test_document_and_board_evidence_come_from_current_tools(
    planning_context, monkeypatch, invalid, streaming
):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert "response_format" not in body
        if len(requests) == 1:
            return wire_response(
                body,
                calls=[
                    tool("search_documents", {"query": "订单规则"}),
                    tool("read_task_board", {}),
                ],
            )
        return wire_response(
            body, f"订单不能重复。[{9 if invalid else 1}] 已安排校验任务。"
        )

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        request = chat.answer(
            planning_context[1],
            planning_context[2],
            ChatRequestQO(question="订单规则和任务是什么？"),
            streaming=streaming,
        )
        if invalid:
            with pytest.raises(ApiError) as error:
                await request
            assert error.value.code == "invalid_chat"
        else:
            result = await request
            assert result.sources[0].document_id == planning_context[3]
            assert result.tasks[0].id == planning_context[4]
            assert result.basis == "project"
            assert {call.name for call in result.tool_calls} == {
                "search_documents",
                "read_task_board",
            }
    assert len(requests) == 2


@pytest.mark.parametrize(
    "answer,finish",
    [
        ("", "stop"),
        ("  ", "stop"),
        ("字" * 4001, "stop"),
        ("未写完", "length"),
        ("被过滤", "content_filter"),
        ("重复重复", "repetition_truncation"),
        ("没有读取却声称引用了资料。[1]", "stop"),
    ],
)
async def test_invalid_answer_is_rejected_without_extra_generation(
    planning_context, monkeypatch, answer, finish
):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        return wire_response(body, answer, finish=finish)

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        with pytest.raises(ApiError) as error:
            await ask(chat, planning_context)
        assert error.value.code == "invalid_chat" and not chat._slots.locked()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "answer",
    [
        "Python 中 items[1] 表示第二个元素。",
        "引用格式示例：`[1]`。",
        "示例：\n```python\nitems = [1]\n```",
        "参考这个[1](https://example.invalid)链接。",
    ],
)
async def test_code_and_link_numbers_are_not_document_citations(
    planning_context, monkeypatch, answer
):
    def respond(request):
        return wire_response(json.loads(request.content), answer)

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        result = await ask(chat, planning_context)
    assert result.answer == answer and not result.sources


async def test_missing_document_citations_fail_after_streamed_preview(
    planning_context, monkeypatch
):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return wire_response(
                body, calls=[tool("search_documents", {"query": "订单"})]
            )
        return wire_response(body, "订单不能重复，但忘记附引用了。")

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:

        async def run(events):
            return await chat.answer(
                planning_context[1],
                planning_context[2],
                ChatRequestQO(question="订单规则？"),
                events=events,
                streaming=True,
            )

        events = [
            json.loads(line)
            async for line in StreamRunner(run, "chat", "mimo-invalid").stream()
        ]
    assert any(e["type"] == "token" for e in events)
    assert not any(e["type"] == "final" for e in events)
    assert (
        events[-1]["type"] == "error" and events[-1]["error"]["code"] == "invalid_chat"
    )


@pytest.mark.parametrize("board", [False, True])
async def test_empty_search_is_insufficient_but_empty_board_is_valid(
    planning_context, monkeypatch, board
):
    async with planning_context[0].begin() as session:
        await session.execute(delete(TaskDO if board else DocumentDO))
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            call = (
                tool("read_task_board", {})
                if board
                else tool("search_documents", {"query": "订单规则"})
            )
            return wire_response(body, calls=[call])
        return wire_response(
            body, "当前没有任务。" if board else "当前没有可用资料，无法确认项目规则。"
        )

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        result = await ask(chat, planning_context)
    assert result.basis == "project" and not result.sources and not result.tasks
    assert result.status == ("answered" if board else "insufficient_evidence")


async def test_fifth_model_call_only_generates_final_text(
    planning_context, monkeypatch
):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert "response_format" not in body
        if len(requests) <= 3:
            return wire_response(
                body, calls=[tool("search_documents", {"query": "规则"})]
            )
        if len(requests) == 4:
            return wire_response(body, calls=[tool("read_task_board", {})])
        assert len(requests) == 5 and not body.get("tools")
        return wire_response(body, "订单不能重复。[1]")

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        assert (await ask(chat, planning_context, "订单规则？")).sources
    assert len(requests) == 5


async def test_failed_answer_does_not_enter_persistent_history(
    planning_context, monkeypatch
):
    requests = []
    fail = False

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        return wire_response(body, "错误引用。[9]" if fail else "珠海市位于广东省。")

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        sessions = ChatSessionService(planning_context[0], chat)
        owner, project = planning_context[1:3]
        row = await sessions.create(owner, project)
        await sessions.answer(
            owner,
            project,
            row.id,
            SessionMessageQO(question="珠海市", client_message_id=uuid4()),
        )
        fail = True
        retry = SessionMessageQO(question="继续", client_message_id=uuid4())
        with pytest.raises(ApiError):
            await sessions.answer(owner, project, row.id, retry)
        fail = False
        await sessions.answer(owner, project, row.id, retry)
        messages = requests[-1]["messages"]
        assert [m["content"] for m in messages if m["role"] == "assistant"] == [
            "珠海市位于广东省。"
        ]
        assert [m["content"] for m in messages if m["role"] == "user"] == [
            "珠海市",
            "继续",
        ]
        saved = await sessions.get(owner, project, row.id)
        assert all(m.status == "completed" for m in saved.messages)
    assert len(requests) == 3


async def test_existing_structured_checkpoint_can_continue_as_text(
    planning_context, monkeypatch
):
    saver = InMemorySaver()
    old_chat = legacy_service(planning_context, finish("你好，小明。"), saver=saver)
    old_sessions = ChatSessionService(planning_context[0], old_chat)
    owner, project = planning_context[1:3]
    row = await old_sessions.create(owner, project)
    await old_sessions.answer(
        owner,
        project,
        row.id,
        SessionMessageQO(question="我叫小明", client_message_id=uuid4()),
    )

    def respond(request):
        body = json.loads(request.content)
        assert any(m["role"] == "tool" for m in body["messages"])
        assert "ChatCompletion" not in {t["function"]["name"] for t in body["tools"]}
        return wire_response(body, "你叫小明。")

    async with mimo_chat(planning_context, monkeypatch, respond, saver=saver) as chat:
        sessions = ChatSessionService(planning_context[0], chat)
        result = await sessions.answer(
            owner,
            project,
            row.id,
            SessionMessageQO(question="我叫什么？", client_message_id=uuid4()),
        )
        assert result.answer == "你叫小明。"


async def test_previous_turn_citations_cannot_be_reused_without_search(
    planning_context, monkeypatch
):
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return wire_response(
                body, calls=[tool("search_documents", {"query": "订单规则"})]
            )
        return wire_response(body, "订单不能重复。[1]")

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        sessions = ChatSessionService(planning_context[0], chat)
        owner, project = planning_context[1:3]
        row = await sessions.create(owner, project)
        await sessions.answer(
            owner,
            project,
            row.id,
            SessionMessageQO(question="订单规则？", client_message_id=uuid4()),
        )
        with pytest.raises(ApiError) as error:
            await sessions.answer(
                owner,
                project,
                row.id,
                SessionMessageQO(question="继续解释", client_message_id=uuid4()),
            )
        assert error.value.code == "invalid_chat"


async def test_cancelling_generation_releases_chat_slot(planning_context, monkeypatch):
    started, stopped = asyncio.Event(), asyncio.Event()

    async def respond(request):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async with mimo_chat(planning_context, monkeypatch, respond) as chat:
        running = asyncio.create_task(ask(chat, planning_context))
        try:
            await asyncio.wait_for(started.wait(), 5)
        finally:
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
        assert stopped.is_set() and not chat._slots.locked()


@pytest.mark.parametrize(
    "mode,url,expected",
    [
        ("live", "https://api.xiaomimimo.com/v1", True),
        ("live", "https://api.xiaomimimo.com/v1/", True),
        ("mock", "https://api.xiaomimimo.com/v1", False),
        ("live", "https://api.xiaomimimo.com.example.invalid/v1", False),
        ("live", "https://example.invalid/v1", False),
    ],
)
def test_text_protocol_is_scoped_to_live_official_mimo(mode, url, expected):
    assert (
        uses_mimo_auto_tools(configuration(ai_mode=mode, llm_base_url=url)) is expected
    )
