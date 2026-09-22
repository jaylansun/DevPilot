import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from app.schemas.workflow_vo import TaskLookupVO
from app.services.planning_read_service import PlanningReadService
from app.services.run_stream_service import StreamRunner
from test_planning_tools import planning_context as _planning_context
from test_workflow import build_service, run

planning_context = _planning_context


@pytest.mark.parametrize("failure", ["retrieval", "cancel"])
async def test_parallel_graph_cancels_remaining_branch_without_generating_report(
    planning_context, monkeypatch, failure
):
    board_started, board_cancelled, search_cancelled = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    model = AsyncMock()
    service = build_service(planning_context, live=True, model=model)

    async def board(*_):
        board_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            board_cancelled.set()

    async def search(*_):
        await board_started.wait()
        try:
            if failure == "retrieval":
                raise ConnectionError("private-retrieval-payload")
            await asyncio.Event().wait()
        finally:
            search_cancelled.set()

    with monkeypatch.context() as patch:
        patch.setattr(PlanningReadService, "read_task_board", board)
        patch.setattr(PlanningReadService, "search_documents", search)
        runner = StreamRunner(
            lambda events: run(
                planning_context, service, intent="requirement_check", events=events
            ),
            "workflow",
            "parallel-failure",
        )
        stream = runner.stream()
        if failure == "retrieval":
            events = await asyncio.wait_for(_collect(stream), 3)
            assert events[-1]["type"] == "error"
            assert events[-1]["error"]["code"] == "workflow_unavailable"
            assert "private-retrieval-payload" not in json.dumps(events)
            assert not any(e.get("name") == "generate_report" for e in events)
        else:
            # 在消费者收到两条并行节点 started 后关闭流，模拟前端停止读取。
            while not board_started.is_set():
                await asyncio.wait_for(anext(stream), 3)
            await stream.aclose()
        assert board_cancelled.is_set() and search_cancelled.is_set()
        model.report.assert_not_awaited()
        assert service._slots._value == 1
    # 下一次请求可以重新取得名额，并使用完整的正常读取器。
    model.lookup.return_value = TaskLookupVO(
        summary="恢复读取", task_ids=[planning_context[4]]
    )
    result = await run(planning_context, service, intent="task_lookup")
    assert result.tasks[0].id == planning_context[4]


async def _collect(stream):
    return [json.loads(line) async for line in stream]
