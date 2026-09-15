from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field
from test_plan_schema import proposal_data

from app.errors import ApiError
from app.services.plan_agent_service import build_planning_agent
from app.tools.planning_tools import PlanToolContext


class ScriptedPlanningModel(BaseChatModel):
    """真实 Agent/ToolRuntime 集成测试中的离线模型，不发送网络请求。"""

    replies: list[AIMessage]
    calls: int = 0
    bound: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "离线规划模型"

    def bind_tools(self, tools, **kwargs):
        self.bound = list(tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = self.replies[min(self.calls, len(self.replies) - 1)].model_copy(
            deep=True
        )
        message.id = None
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def tool_reply(round_number=1, *, include_board=True):
    calls = [
        {
            "name": "search_documents",
            "args": {"query": "订单规则"},
            "id": f"search-{round_number}",
            "type": "tool_call",
        },
    ]
    if include_board:
        calls.append(
            {
                "name": "read_task_board",
                "args": {},
                "id": f"board-{round_number}",
                "type": "tool_call",
            }
        )
    return AIMessage(content="", tool_calls=calls)


def final_reply(data=None):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "PlanProposalVO",
                "args": data or proposal_data(),
                "id": "plan-1",
                "type": "tool_call",
            }
        ],
    )


def tool_context():
    reader = Mock()
    reader.search_documents = AsyncMock(
        return_value={"sources": [{"source_id": 1, "text": "库存不足不允许下单"}]}
    )
    reader.read_task_board = AsyncMock(return_value={"tasks": [], "total": 0})
    return PlanToolContext(uuid4(), uuid4(), reader)


async def test_actual_agent_tools_runtime_and_structured_output():
    context = tool_context()
    model = ScriptedPlanningModel(replies=[tool_reply(), final_reply()])
    agent = build_planning_agent(model)
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "拆解订单任务"}]}, context=context
    )
    assert result["structured_response"].tasks[0].draft_id == "T1"
    context.reader.search_documents.assert_awaited_once_with(
        context.owner_id, context.project_id, "订单规则"
    )
    context.reader.read_task_board.assert_awaited_once_with(
        context.owner_id, context.project_id
    )
    assert model.calls == 2


async def test_tool_transient_failure_retries_once_only():
    context = tool_context()
    context.reader.search_documents.side_effect = [TimeoutError(), {"sources": []}]
    model = ScriptedPlanningModel(replies=[tool_reply(), final_reply()])
    await build_planning_agent(model).ainvoke(
        {"messages": [{"role": "user", "content": "订单"}]}, context=context
    )
    assert context.reader.search_documents.await_count == 2


async def test_tool_permission_error_is_not_retried():
    context = tool_context()
    context.reader.search_documents.side_effect = ApiError(
        404, "project_not_found", "项目不存在"
    )
    model = ScriptedPlanningModel(replies=[tool_reply(), final_reply()])
    with pytest.raises(ApiError):
        await build_planning_agent(model).ainvoke(
            {"messages": [{"role": "user", "content": "订单"}]}, context=context
        )
    assert context.reader.search_documents.await_count == 1


async def test_agent_without_structured_result_stops():
    context = tool_context()
    model = ScriptedPlanningModel(replies=[AIMessage(content="继续思考，不调用工具")])
    result = await build_planning_agent(model).ainvoke(
        {"messages": [{"role": "user", "content": "订单"}]},
        context=context,
        config={"recursion_limit": 24},
    )
    assert result.get("structured_response") is None
    assert model.calls <= 4


async def test_repeated_model_calls_are_bounded():
    context = tool_context()
    reply = AIMessage(
        content="",
        tool_calls=[
            {"name": "read_task_board", "args": {}, "id": "board", "type": "tool_call"}
        ],
    )
    model = ScriptedPlanningModel(replies=[reply])
    with pytest.raises(ModelCallLimitExceededError):
        await build_planning_agent(model).ainvoke(
            {"messages": [{"role": "user", "content": "订单"}]},
            context=context,
            config={"recursion_limit": 24},
        )
    assert model.calls == 4
    assert context.reader.read_task_board.await_count == 4


async def test_repeated_tool_calls_are_bounded():
    context = tool_context()
    model = ScriptedPlanningModel(replies=[tool_reply()])
    with pytest.raises(ToolCallLimitExceededError):
        await build_planning_agent(model).ainvoke(
            {"messages": [{"role": "user", "content": "订单"}]},
            context=context,
            config={"recursion_limit": 24},
        )
    assert (
        context.reader.read_task_board.await_count
        + context.reader.search_documents.await_count
        <= 6
    )


async def test_five_reads_leave_one_call_for_structured_output():
    """四轮模型按 2、2、1 次读取及 1 次结果提交，恰好用完总预算。"""
    context = tool_context()
    model = ScriptedPlanningModel(
        replies=[
            tool_reply(1),
            tool_reply(2),
            tool_reply(3, include_board=False),
            final_reply(),
        ]
    )
    result = await build_planning_agent(model).ainvoke(
        {"messages": [{"role": "user", "content": "订单"}]},
        context=context,
        config={"recursion_limit": 24},
    )
    assert result["structured_response"].model_dump() == proposal_data()
    assert context.reader.search_documents.await_count == 3
    assert context.reader.read_task_board.await_count == 2
    assert model.calls == 4


async def test_six_reads_exhaust_budget_before_structured_output():
    """模型次数仍在四次上限内，但结果提交是第七次工具调用，应被拒绝。"""
    context = tool_context()
    model = ScriptedPlanningModel(
        replies=[tool_reply(1), tool_reply(2), tool_reply(3), final_reply()]
    )
    with pytest.raises(ToolCallLimitExceededError) as error:
        await build_planning_agent(model).ainvoke(
            {"messages": [{"role": "user", "content": "订单"}]},
            context=context,
            config={"recursion_limit": 24},
        )
    assert error.value.run_count == 7
    assert error.value.run_limit == 6
    assert context.reader.search_documents.await_count == 3
    assert context.reader.read_task_board.await_count == 3
    assert model.calls == 4


async def test_invalid_structured_output_does_not_retry_forever():
    context = tool_context()
    data = proposal_data()
    data["tasks"][0]["dependencies"] = ["T2"]
    model = ScriptedPlanningModel(replies=[tool_reply(), final_reply(data)])
    with pytest.raises(Exception) as error:
        await build_planning_agent(model).ainvoke(
            {"messages": [{"role": "user", "content": "订单"}]}, context=context
        )
    assert "structured" in type(error.value).__name__.lower()
    assert model.calls == 2
