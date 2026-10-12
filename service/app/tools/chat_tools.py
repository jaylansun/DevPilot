"""聊天只读工具；身份和本轮证据通过框架运行上下文传入。"""

from dataclasses import dataclass, field
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chat_vo import ChatCheckArtifactVO, ChatPlanArtifactVO
from app.services.chat_business_service import run_requirement_check, run_task_planning
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
    planner: object | None = None
    workflow: object | None = None
    artifacts: list[ChatPlanArtifactVO | ChatCheckArtifactVO] = field(
        default_factory=list
    )
    artifact_readers: list[PlanningReadService] = field(default_factory=list)
    business_calls: set[str] = field(default_factory=set)


class ReadInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid", arbitrary_types_allowed=True, str_strip_whitespace=True
    )
    runtime: ToolRuntime[ChatToolContext]


class SearchInput(ReadInput):
    query: str = Field(min_length=1, max_length=2000)


class PlanInput(ReadInput):
    goal: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class CheckInput(ReadInput):
    scope: str = Field(min_length=1, max_length=2000, pattern=r"\S")


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


@tool(args_schema=PlanInput)
async def generate_task_plan(goal: str, runtime: ToolRuntime[ChatToolContext]) -> dict:
    """根据当前项目资料和看板生成任务草案，返回独立结果供用户展开审核。每轮最多一次；不会创建任务或提交审批。"""
    return await run_task_planning(runtime.context, goal)


@tool(args_schema=CheckInput)
async def check_requirements(scope: str, runtime: ToolRuntime[ChatToolContext]) -> dict:
    """对照当前项目需求片段与看板检查覆盖、遗漏和待确认问题，返回独立报告。每轮最多一次；不修改任务。"""
    return await run_requirement_check(runtime.context, scope)


def available_chat_tools(context: ChatToolContext):
    tools = list(CHAT_TOOLS)
    if context.planner is not None:
        tools.append(generate_task_plan)
    if context.workflow is not None:
        tools.append(check_requirements)
    return tools
