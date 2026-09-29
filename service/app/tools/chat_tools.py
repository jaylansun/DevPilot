"""聊天只读工具；身份和本轮证据通过框架运行上下文传入。"""

from dataclasses import dataclass
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, ConfigDict, Field

from app.services.planning_read_service import PlanningReadService
from app.services.run_events import EventPublisher, trace


@dataclass
class ChatToolContext:
    owner: UUID
    project: UUID
    reader: PlanningReadService
    board_reader: PlanningReadService
    events: EventPublisher
    board: dict | None = None


class ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    runtime: ToolRuntime[ChatToolContext]


class SearchInput(ReadInput):
    query: str = Field(min_length=1, max_length=2000)


@tool(args_schema=SearchInput)
async def search_documents(query: str, runtime: ToolRuntime[ChatToolContext]) -> dict:
    """搜索当前项目的需求文档、业务规则和设计。项目事实或相关追问前使用；通用知识和问候不需要。空结果表示缺少依据。"""
    context = runtime.context
    async with trace(context.events, "search_documents", kind="tool"):
        return await context.reader.search_documents(
            context.owner, context.project, query
        )


@tool(args_schema=ReadInput)
async def read_task_board(runtime: ToolRuntime[ChatToolContext]) -> dict:
    """查询当前项目已有任务的标题、状态、优先级和说明。回答任务安排、进度或数量时使用；最多完整读取100项，任务存在不代表已实现。"""
    context = runtime.context
    async with trace(context.events, "read_task_board", kind="tool"):
        context.board = await context.board_reader.read_task_board(
            context.owner, context.project
        )
        context.reader.tool_calls.append(context.board_reader.tool_calls[-1])
        return context.board


CHAT_TOOLS = [search_documents, read_task_board]
