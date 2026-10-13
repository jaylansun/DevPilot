"""真实 OpenAI SDK 的离线 wire 回归：规划阶段收敛及流式请求总时限。"""

import asyncio
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_chat_mimo import tool, wire_response
from test_plan_schema import proposal_data
from test_planning_tools import planning_context as _planning_context
from test_rag_model import configuration

from app.errors import ApiError
from app.schemas.chat_qo import ChatRequestQO
from app.services.chat_model_service import ChatModelService
from app.services.chat_service import ChatService
from app.services.plan_agent_service import PlanAgentService
from app.services.plan_service import PlanService
from app.services.run_stream_service import StreamRunner

planning_context = _planning_context
TEST_KEY = "synthetic-planning-test-key"
GOAL = "规划订单模块的开发任务"


def advertised_tools(body):
    return [entry["function"]["name"] for entry in body.get("tools", [])]


def is_planning(body):
    return "项目任务规划助手" in body["messages"][0]["content"]


@asynccontextmanager
async def mimo_planning_chat(context, monkeypatch, respond):
    """保留真实 Agent、读取器与 SDK，仅替换底层 HTTP transport。"""
    from langchain_openai import ChatOpenAI

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

        def model(**kwargs):
            return ChatOpenAI(**kwargs, http_async_client=client)

        monkeypatch.setattr("langchain_openai.ChatOpenAI", model)
        monkeypatch.setattr("app.services.plan_agent_service.ChatOpenAI", model)
        settings = configuration(
            ai_mode="live",
            model_name="mimo-v2.5",
            llm_api_key=TEST_KEY,
            llm_base_url="https://api.xiaomimimo.com/v1",
        )
        planner = PlanService(
            settings, context[5], context[0], PlanAgentService(settings)
        )
        chat = ChatService(
            settings,
            context[5],
            context[0],
            ChatModelService(settings, InMemorySaver()),
            planner=planner,
        )
        yield chat, planner


async def streamed_chat(chat, context, *, intent="auto", request_id="plan-wire"):
    async def run(events):
        return await chat.answer(
            *context[1:3],
            ChatRequestQO(question=GOAL, intent=intent),
            events=events,
            streaming=True,
        )

    return [
        json.loads(line)
        async for line in StreamRunner(run, "chat", request_id).stream()
    ]


def parent_response(body):
    if "generate_task_plan" in advertised_tools(body):
        return wire_response(body, calls=[tool("generate_task_plan", {"goal": GOAL})])
    return wire_response(body, "已生成订单开发任务草案，请查看结果。")


@pytest.mark.parametrize("intent", ["auto", "task_planning"])
@pytest.mark.parametrize("repair", [False, True])
async def test_required_reads_are_followed_by_only_final_tool_on_real_wire(
    planning_context, monkeypatch, intent, repair
):
    """有证据后只保留终稿工具，供应商没有继续检索的选择。"""
    plan_requests, parent_requests = [], []
    final_count = 0

    def respond(request):
        nonlocal final_count
        body = json.loads(request.content)
        names = advertised_tools(body)
        assert body["thinking"] == {"type": "disabled"}
        if not is_planning(body):
            parent_requests.append(body)
            return parent_response(body)
        if names == ["search_documents", "read_task_board"]:
            plan_requests.append(body)
            return wire_response(
                body,
                calls=[
                    tool("search_documents", {"query": "订单规则"}),
                    tool("read_task_board", {}),
                ],
            )
        if "PlanProposalVO" in names:
            plan_requests.append(body)
            assert names == ["PlanProposalVO"]
            final_count += 1
            data = proposal_data()
            if repair and final_count == 1:
                data["tasks"][0]["dependencies"] = ["T9"]
            return wire_response(body, calls=[tool("PlanProposalVO", data)])
        raise AssertionError(f"unexpected planning tools: {names}")

    async with mimo_planning_chat(planning_context, monkeypatch, respond) as services:
        chat, planner = services
        events = await streamed_chat(chat, planning_context, intent=intent)
        assert not chat._slots.locked() and not planner._slots.locked()

    assert events[-1]["type"] == "final"
    result = events[-1]["result"]
    assert result["artifacts"][0]["result"]["proposal"] == proposal_data()
    assert [advertised_tools(body) for body in plan_requests] == [
        ["search_documents", "read_task_board"],
        *([["PlanProposalVO"]] * (2 if repair else 1)),
    ]
    assert len(parent_requests) == (2 if intent == "auto" else 0)
    # LangChain 在父 astream 回调中调用子 Agent.ainvoke 时仍会发送 stream=true。
    assert all(
        body.get("stream", False) is (intent == "auto") for body in plan_requests
    )
    planning_context[5].search.assert_called_once()
    tool_calls = result["artifacts"][0]["result"]["tool_calls"]
    assert [entry["name"] for entry in tool_calls] == [
        "search_documents",
        "read_task_board",
    ]
    tokens = "".join(event["text"] for event in events if event["type"] == "token")
    assert "T9" not in tokens and "acceptance_criteria" not in tokens


@pytest.mark.parametrize("intent", ["auto", "task_planning"])
async def test_serial_provider_reads_do_not_spend_extra_search_rounds(
    planning_context, monkeypatch, intent
):
    plan_requests = []

    def respond(request):
        body = json.loads(request.content)
        names = advertised_tools(body)
        if not is_planning(body):
            return parent_response(body)
        if names == ["search_documents", "read_task_board"]:
            plan_requests.append(body)
            return wire_response(
                body, calls=[tool("search_documents", {"query": "订单规则"})]
            )
        if names == ["read_task_board"]:
            plan_requests.append(body)
            return wire_response(body, calls=[tool("read_task_board", {})])
        assert names == ["PlanProposalVO"]
        plan_requests.append(body)
        return wire_response(body, calls=[tool("PlanProposalVO", proposal_data())])

    async with mimo_planning_chat(planning_context, monkeypatch, respond) as services:
        events = await streamed_chat(services[0], planning_context, intent=intent)
    assert events[-1]["type"] == "final"
    assert [advertised_tools(body) for body in plan_requests] == [
        ["search_documents", "read_task_board"],
        ["read_task_board"],
        ["PlanProposalVO"],
    ]
    planning_context[5].search.assert_called_once()


class ContinuousSSE(httpx.AsyncByteStream):
    """持续有 token，单次读未超时，但请求永远没有完成。"""

    def __init__(self):
        self.id = str(uuid4())
        self.chunks = 0
        self.cancelled = False
        self.closed = False

    async def __aiter__(self):
        try:
            while True:
                self.chunks += 1
                frame = {
                    "id": self.id,
                    "created": 1,
                    "model": "mimo-v2.5",
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": None,
                            "delta": {"content": "继续规划"},
                        }
                    ],
                }
                yield f"data: {json.dumps(frame)}\n\n".encode()
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def aclose(self):
        self.closed = True


async def test_continuous_sse_hits_whole_planning_deadline_and_retry_succeeds(
    planning_context, monkeypatch
):
    monkeypatch.setattr("app.services.plan_service.PLANNING_TIMEOUT_SECONDS", 0.3)
    slow = ContinuousSSE()
    stall = True

    def respond(request):
        body = json.loads(request.content)
        names = advertised_tools(body)
        if not is_planning(body):
            return parent_response(body)
        if names == ["search_documents", "read_task_board"]:
            return wire_response(
                body,
                calls=[
                    tool("search_documents", {"query": "订单规则"}),
                    tool("read_task_board", {}),
                ],
            )
        if "PlanProposalVO" in names:
            assert names == ["PlanProposalVO"] and body["stream"] is True
            if stall:
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/event-stream"},
                    stream=slow,
                )
            return wire_response(body, calls=[tool("PlanProposalVO", proposal_data())])
        raise AssertionError(f"unexpected planning tools: {names}")

    async with mimo_planning_chat(planning_context, monkeypatch, respond) as services:
        chat, planner = services
        events = await asyncio.wait_for(streamed_chat(chat, planning_context), 3)
        assert events[-1]["type"] == "error"
        assert events[-1]["error"]["code"] == "planning_timeout"
        assert not any(event["type"] == "final" for event in events)
        assert slow.chunks > 1 and slow.cancelled and slow.closed
        assert not chat._slots.locked() and not planner._slots.locked()
        stall = False
        retry = await streamed_chat(chat, planning_context, request_id="plan-retry")
        assert retry[-1]["type"] == "final"
        assert not chat._slots.locked() and not planner._slots.locked()


async def test_sdk_io_timeout_is_safe_and_releases_both_execution_slots(
    planning_context, monkeypatch, caplog
):
    fail = True
    provider_detail = f"provider internal details: {TEST_KEY}"
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        names = advertised_tools(body)
        if not is_planning(body):
            return parent_response(body)
        if fail:
            raise httpx.ReadTimeout(provider_detail, request=request)
        if "PlanProposalVO" in names:
            return wire_response(body, calls=[tool("PlanProposalVO", proposal_data())])
        if names == ["search_documents", "read_task_board"]:
            return wire_response(
                body,
                calls=[
                    tool("search_documents", {"query": "订单规则"}),
                    tool("read_task_board", {}),
                ],
            )
        raise AssertionError(f"unexpected planning tools: {names}")

    async with mimo_planning_chat(planning_context, monkeypatch, respond) as services:
        chat, planner = services
        with pytest.raises(ApiError) as error:
            await chat.answer(
                *planning_context[1:3],
                ChatRequestQO(question=GOAL, intent="task_planning"),
            )
        assert error.value.code == "planning_timeout"
        assert error.value.status_code == 504
        assert TEST_KEY not in str(error.value.message)
        assert provider_detail not in caplog.text and TEST_KEY not in caplog.text
        assert len(requests) == 1  # SDK max_retries=0，无额外请求。
        assert not chat._slots.locked() and not planner._slots.locked()
        fail = False
        result = await chat.answer(
            *planning_context[1:3],
            ChatRequestQO(question=GOAL, intent="task_planning"),
        )
        assert result.artifacts[0].result.proposal.tasks
        assert not chat._slots.locked() and not planner._slots.locked()
