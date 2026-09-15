import asyncio
import json
import threading
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError
from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolInvocationError
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO, TaskStatus
from app.models.user_do import UserDO, UserRole
from app.services.document_index_service import RetrievedChunk
from app.services.planning_read_service import PlanningReadService
from app.tools.planning_tools import PLANNING_TOOLS, PlanToolContext


@pytest.fixture
async def planning_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'planning.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, project, doc, task_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with factory.begin() as session:
        session.add(
            UserDO(
                id=owner,
                username="规划工具测试",
                password_hash="测试",
                role=UserRole.MEMBER,
            )
        )
        await session.flush()
        session.add(ProjectDO(id=project, owner_id=owner, name="规划项目"))
        await session.flush()
        session.add_all(
            [
                DocumentDO(
                    id=doc,
                    project_id=project,
                    filename="项目规则.md",
                    content="提交订单不能重复。",
                    content_hash="a" * 64,
                    size_bytes=30,
                    status=DocumentStatus.READY,
                    chunk_count=20,
                ),
                TaskDO(
                    id=task_id,
                    project_id=project,
                    title="实现已有订单校验",
                    description="已有任务说明",
                    acceptance_criteria="重复提交应被拒绝",
                    priority=2,
                    status=TaskStatus.IN_PROGRESS,
                ),
            ]
        )
    index = Mock()
    index.search.return_value = [
        RetrievedChunk(doc, 0, "提交订单不能重复。", "规则", 0.9)
    ]
    yield factory, owner, project, doc, task_id, index, engine
    await engine.dispose()


def tool_graph():
    graph = StateGraph(MessagesState, context_schema=PlanToolContext)
    graph.add_node("tools", ToolNode(PLANNING_TOOLS, handle_tool_errors=False))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile()


async def invoke_tools(context, calls):
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{i}", "type": "tool_call"}
            for i, (name, args) in enumerate(calls)
        ],
    )
    return await tool_graph().ainvoke({"messages": [message]}, context=context)


def test_real_tool_schemas_hide_runtime_and_identity():
    search_schema, board_schema = [
        convert_to_openai_tool(item)["function"]["parameters"]
        for item in PLANNING_TOOLS
    ]
    assert set(search_schema["properties"]) == {"query"}
    assert search_schema["properties"]["query"]["minLength"] == 1
    assert search_schema["properties"]["query"]["maxLength"] == 2000
    assert board_schema["properties"] == {}
    for schema in (search_schema, board_schema):
        assert "runtime" not in json.dumps(schema)
        assert "owner_id" not in json.dumps(schema)
        assert "project_id" not in json.dumps(schema)
    assert all(
        item.args_schema.model_config["extra"] == "forbid" for item in PLANNING_TOOLS
    )


async def test_real_tool_node_injects_frozen_authenticated_context(planning_context):
    factory, owner, project, _doc, _task, index, _engine = planning_context
    reader = PlanningReadService(factory, index)
    context = PlanToolContext(owner, project, reader)
    with pytest.raises(FrozenInstanceError):
        context.owner_id = uuid4()
    result = await invoke_tools(
        context,
        [("search_documents", {"query": "订单约束"}), ("read_task_board", {})],
    )
    messages = result["messages"][1:]
    assert len(messages) == 2
    assert all(message.status == "success" for message in messages)
    assert {entry["name"] for entry in reader.tool_calls} == {
        "search_documents",
        "read_task_board",
    }
    assert reader.sources[0].source_id == 1
    assert reader.board_task_count == 1


@pytest.mark.parametrize("field", ["owner_id", "user_id", "project_id", "sql", "path"])
@pytest.mark.parametrize("name", ["search_documents", "read_task_board"])
async def test_tool_node_rejects_model_identity_or_execution_parameters(
    planning_context, field, name
):
    factory, owner, project, _doc, _task, index, _engine = planning_context
    reader = PlanningReadService(factory, index)
    args = {field: str(uuid4())}
    if name == "search_documents":
        args["query"] = "订单约束"
    with pytest.raises(ToolInvocationError) as error:
        await invoke_tools(PlanToolContext(owner, project, reader), [(name, args)])
    assert isinstance(error.value.__cause__, ValidationError)
    assert field in str(error.value)
    index.search.assert_not_called()
    assert reader.tool_calls == []


@pytest.mark.parametrize(
    "query", ["", "字" * 2001, 123, None], ids=["empty", "too_long", "number", "null"]
)
async def test_tool_node_validates_query_before_reading(planning_context, query):
    factory, owner, project, _doc, _task, index, _engine = planning_context
    reader = PlanningReadService(factory, index)
    with pytest.raises(ToolInvocationError) as error:
        await invoke_tools(
            PlanToolContext(owner, project, reader),
            [("search_documents", {"query": query})],
        )
    assert isinstance(error.value.__cause__, ValidationError)
    index.search.assert_not_called()


async def test_forged_runtime_is_overwritten_by_real_tool_node(planning_context):
    factory, owner, project, _doc, _task, index, _engine = planning_context
    reader = PlanningReadService(factory, index)
    result = await invoke_tools(
        PlanToolContext(owner, project, reader),
        [
            (
                "search_documents",
                {
                    "query": "订单规则",
                    "runtime": {"context": {"owner_id": str(uuid4())}},
                },
            )
        ],
    )
    assert result["messages"][-1].status == "success"
    assert index.search.call_args.args[0] == project


@pytest.mark.parametrize(
    "method", ["search_documents", "read_task_board", "assert_unchanged"]
)
async def test_cross_project_returns_404_before_retrieval(planning_context, method):
    factory, _owner, project, _doc, _task, index, _engine = planning_context
    reader = PlanningReadService(factory, index)
    arguments = [uuid4(), project]
    if method == "search_documents":
        arguments.append("项目资料")
    with pytest.raises(ApiError) as error:
        await getattr(reader, method)(*arguments)
    assert error.value.status_code == 404
    index.search.assert_not_called()
    assert reader.sources == []


@pytest.mark.parametrize(
    "status", [status for status in DocumentStatus if status != DocumentStatus.READY]
)
async def test_non_ready_documents_are_never_searched(planning_context, status):
    factory, owner, project, doc, _task, index, _engine = planning_context
    async with factory.begin() as session:
        (await session.get(DocumentDO, doc)).status = status
    reader = PlanningReadService(factory, index)
    result = await reader.search_documents(owner, project, "订单规则")
    assert result["status"] == "empty"
    assert result["sources"] == []
    index.search.assert_not_called()
    assert reader.tool_calls == [
        {"name": "search_documents", "status": "empty", "item_count": 0}
    ]


async def test_index_receives_ready_ids_and_unscoped_results_are_filtered(
    planning_context,
):
    factory, owner, project, doc, _task, index, _engine = planning_context
    other_doc = uuid4()
    async with factory.begin() as session:
        session.add(
            DocumentDO(
                id=other_doc,
                project_id=project,
                filename="未就绪.md",
                content="不应读取",
                content_hash="b" * 64,
                size_bytes=12,
                status=DocumentStatus.INDEXING,
            )
        )
    index.search.return_value = [
        RetrievedChunk(other_doc, 0, "未就绪内容", "", 0.9),
        RetrievedChunk(uuid4(), 0, "其他项目内容", "", 0.9),
        RetrievedChunk(doc, 0, "当前就绪内容", "", 0.9),
    ]
    reader = PlanningReadService(factory, index, min_score=0.6)
    result = await reader.search_documents(owner, project, "订单规则")
    assert index.search.call_args.args == (project, [doc], "订单规则")
    assert index.search.call_args.kwargs == {"limit": 4, "min_score": 0.6}
    assert len(result["sources"]) == 1
    assert reader.sources[0].document_id == doc


async def test_sources_are_deduplicated_stable_and_bounded(planning_context):
    factory, owner, project, doc, _task, index, _engine = planning_context
    reader = PlanningReadService(factory, index)
    index.search.return_value = [
        RetrievedChunk(doc, 0, "字" * 450, "标题" * 300, 0.9),
        RetrievedChunk(doc, 0, "重复片段", "", 0.9),
        RetrievedChunk(doc, 1, "第二段", "", 0.9),
    ]
    first = await reader.search_documents(owner, project, "第一次")
    assert [source["source_id"] for source in first["sources"]] == [1, 2]
    assert len(reader.sources[0].text) == 400
    assert len(reader.sources[0].heading) == 400
    index.search.return_value = [
        RetrievedChunk(doc, 1, "第二段", "", 0.9),
        RetrievedChunk(doc, 2, "第三段", "", 0.9),
        RetrievedChunk(doc, 0, "字" * 450, "", 0.9),
    ]
    second = await reader.search_documents(owner, project, "第二次")
    assert [source["source_id"] for source in second["sources"]] == [2, 3, 1]
    for offset in (3, 7, 11):
        index.search.return_value = [
            RetrievedChunk(doc, i, f"资料{i}", "", 0.9)
            for i in range(offset, offset + 4)
        ]
        last = await reader.search_documents(owner, project, "补充")
    assert [source.source_id for source in reader.sources] == list(range(1, 13))
    assert last["truncated"]
    assert last["sources"][0]["source_id"] == 12


async def test_board_preserves_titles_and_marks_excerpt_truncation(planning_context):
    factory, owner, project, _doc, task_id, index, _engine = planning_context
    async with factory.begin() as session:
        task = await session.get(TaskDO, task_id)
        task.title = "标题" * 100
        task.description = "说明" * 300
        task.acceptance_criteria = "验收" * 300
    reader = PlanningReadService(factory, index)
    result = await reader.read_task_board(owner, project)
    task = result["tasks"][0]
    assert task["title"] == "标题" * 100
    assert task["status"] == "in_progress"
    assert task["priority"] == 2
    assert len(task["description"]) == len(task["acceptance_criteria"]) == 400
    assert task["description_truncated"] and task["acceptance_criteria_truncated"]
    assert result["truncated"] and "400" in result["truncation_note"]
    assert reader.existing_titles == ["标题" * 100]
    assert reader.board_task_count == result["total"] == 1


async def test_board_over_limit_is_explicitly_rejected(planning_context):
    factory, owner, project, _doc, _task, index, _engine = planning_context
    async with factory.begin() as session:
        session.add_all(
            TaskDO(project_id=project, title=f"已有任务{i}") for i in range(100)
        )
    reader = PlanningReadService(factory, index)
    with pytest.raises(ApiError) as error:
        await reader.read_task_board(owner, project)
    assert error.value.code == "planning_board_too_large"
    assert "100" in error.value.message
    assert reader.tool_calls == []
    assert reader.existing_titles == []


@pytest.mark.parametrize("count", [0, 100])
async def test_board_reads_all_tasks_at_supported_boundaries(planning_context, count):
    factory, owner, project, _doc, task_id, index, _engine = planning_context
    async with factory.begin() as session:
        if count == 0:
            await session.delete(await session.get(TaskDO, task_id))
        else:
            session.add_all(
                TaskDO(project_id=project, title=f"边界任务{i}")
                for i in range(count - 1)
            )
    reader = PlanningReadService(factory, index)
    result = await reader.read_task_board(owner, project)
    assert result["total"] == len(result["tasks"]) == count
    assert reader.board_task_count == len(reader.existing_titles) == count
    assert result["status"] == ("success" if count else "empty")
    assert reader.tool_calls[0]["item_count"] == count
    await reader.assert_unchanged(owner, project)


async def test_no_retrieval_hits_are_recorded_as_empty(planning_context):
    factory, owner, project, _doc, _task, index, _engine = planning_context
    index.search.return_value = []
    reader = PlanningReadService(factory, index)
    result = await reader.search_documents(owner, project, "没有相关资料的问题")
    assert result["status"] == "empty" and result["sources"] == []
    assert reader.sources == []
    assert reader.tool_calls[0] == {
        "name": "search_documents",
        "status": "empty",
        "item_count": 0,
    }


async def test_reader_cannot_mix_two_owned_projects(planning_context):
    factory, owner, project, _doc, _task, index, _engine = planning_context
    second_project = uuid4()
    async with factory.begin() as session:
        session.add(ProjectDO(id=second_project, owner_id=owner, name="第二个项目"))
    reader = PlanningReadService(factory, index)
    await reader.search_documents(owner, project, "项目规则")
    with pytest.raises(ApiError) as error:
        await reader.read_task_board(owner, second_project)
    assert error.value.code == "planning_context_changed"
    assert reader.existing_titles == []


@pytest.mark.parametrize(
    "change",
    [
        "task",
        "new_task",
        "deleted_task",
        "document_status",
        "document_version",
        "project",
    ],
)
@pytest.mark.parametrize(
    "method", ["assert_unchanged", "read_task_board", "search_documents"]
)
async def test_snapshot_detects_changes_across_independent_sessions(
    planning_context, change, method
):
    factory, owner, project, doc, task_id, index, _engine = planning_context
    reader = PlanningReadService(factory, index)
    await reader.search_documents(owner, project, "首次读取")
    async with factory.begin() as session:
        if change == "task":
            (await session.get(TaskDO, task_id)).status = TaskStatus.DONE
        elif change == "new_task":
            session.add(TaskDO(project_id=project, title="新增任务"))
        elif change == "deleted_task":
            await session.delete(await session.get(TaskDO, task_id))
        elif change == "document_status":
            (await session.get(DocumentDO, doc)).status = DocumentStatus.DELETING
        elif change == "document_version":
            document = await session.get(DocumentDO, doc)
            document.updated_at += timedelta(seconds=1)
            document.content_hash = "c" * 64
        else:
            (await session.get(ProjectDO, project)).description = "范围发生变化"
    args = [owner, project]
    if method == "search_documents":
        args.append("再次检索")
    with pytest.raises(ApiError) as error:
        await getattr(reader, method)(*args)
    assert error.value.status_code == 409
    assert error.value.code == "planning_context_changed"
    assert index.search.call_count == 1


async def test_document_changed_during_threaded_retrieval_is_rejected(planning_context):
    factory, owner, project, doc, _task, index, _engine = planning_context
    started, release = threading.Event(), threading.Event()

    def search(*_args, **_kwargs):
        started.set()
        assert release.wait(5)
        return [RetrievedChunk(doc, 0, "即将删除的内容", "", 0.9)]

    index.search.side_effect = search
    reader = PlanningReadService(factory, index)
    running = asyncio.create_task(reader.search_documents(owner, project, "订单规则"))
    try:
        assert await asyncio.wait_for(asyncio.to_thread(started.wait, 3), 4)
        async with factory.begin() as session:
            (await session.get(DocumentDO, doc)).status = DocumentStatus.DELETING
    finally:
        release.set()
    with pytest.raises(ApiError) as error:
        await running
    assert error.value.code == "planning_context_changed"
    assert reader.sources == []
    assert reader.tool_calls == []


async def test_concurrent_tools_use_distinct_sessions_and_do_not_write(
    planning_context,
):
    factory, owner, project, _doc, task_id, index, engine = planning_context
    sessions, statements = [], []
    active = 0
    peak_active = 0

    @asynccontextmanager
    async def isolated_factory():
        nonlocal active, peak_active
        async with factory() as session:
            sessions.append(session)
            active += 1
            peak_active = max(peak_active, active)
            try:
                yield session
            finally:
                active -= 1

    def record_sql(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.strip().split()[0].upper())

    event.listen(engine.sync_engine, "before_cursor_execute", record_sql)
    reader = PlanningReadService(isolated_factory, index)
    try:
        await asyncio.gather(
            reader.search_documents(owner, project, "订单规则"),
            reader.search_documents(owner, project, "补充规则"),
            reader.read_task_board(owner, project),
        )
        await reader.assert_unchanged(owner, project)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_sql)
    assert len(sessions) == len({id(session) for session in sessions}) == 7
    assert active == 0 and peak_active == 1
    assert statements and set(statements) == {"SELECT"}
    assert len(reader.sources) == 1
    assert len(reader.tool_calls) == 3
    async with factory() as session:
        tasks = list(await session.scalars(select(TaskDO)))
        assert len(tasks) == 1
        assert tasks[0].id == task_id and tasks[0].version == 1


async def test_cancelled_tool_releases_instance_lock(planning_context):
    factory, owner, project, _doc, _task, index, _engine = planning_context
    reader = PlanningReadService(factory, index)
    original_read = reader._read_context
    entered = asyncio.Event()

    async def blocked_read(*_args):
        entered.set()
        await asyncio.Event().wait()

    reader._read_context = AsyncMock(side_effect=blocked_read)
    running = asyncio.create_task(reader.read_task_board(owner, project))
    await asyncio.wait_for(entered.wait(), 2)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    reader._read_context = original_read
    result = await asyncio.wait_for(reader.read_task_board(owner, project), 3)
    assert result["total"] == 1
