from dataclasses import dataclass
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, ConfigDict, Field

from app.services.planning_read_service import PlanningReadService
from app.services.run_stream_service import trace


@dataclass(frozen=True)
class PlanToolContext:
    """由接口登录身份构造，运行期间不可替换所属用户或项目。"""

    owner_id: UUID
    project_id: UUID
    reader: PlanningReadService


class _ReadToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    # LangGraph 先注入 runtime 再验证；框架会将该类型从模型工具结构中隐藏。
    runtime: ToolRuntime[PlanToolContext]


class _SearchDocumentsInput(_ReadToolInput):
    query: str = Field(
        min_length=1,
        max_length=2000,
        description="用于检索当前项目已就绪文档的自然语言问题，1 至 2000 个字符",
    )


@tool(args_schema=_SearchDocumentsInput)
async def search_documents(query: str, runtime: ToolRuntime[PlanToolContext]) -> dict:
    """只读检索当前项目已就绪文档，返回带稳定引用编号的原文片段；无资料时明确返回空结果。"""
    context = runtime.context
    async with trace("search_documents", kind="tool"):
        return await context.reader.search_documents(
            context.owner_id, context.project_id, query
        )


@tool(args_schema=_ReadToolInput)
async def read_task_board(runtime: ToolRuntime[PlanToolContext]) -> dict:
    """只读当前项目全部任务的标题、状态、优先级及说明，用于避免重复规划；不接受额外参数。"""
    context = runtime.context
    async with trace("read_task_board", kind="tool"):
        return await context.reader.read_task_board(
            context.owner_id, context.project_id
        )


PLANNING_TOOLS = [search_documents, read_task_board]
