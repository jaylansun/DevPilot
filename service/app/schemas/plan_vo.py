from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.rag_vo import RagSourceVO

DraftId = Annotated[str, Field(pattern=r"^T(?:[1-9]|1[0-2])$")]
SourceId = Annotated[int, Field(strict=True, ge=1, le=12)]
PlanNote = Annotated[str, Field(min_length=1, max_length=500)]


def normalize_task_title(title: str) -> str:
    """仅用于识别重复标题，不替换用户实际看到的标题。"""
    return " ".join(title.split()).casefold()


class TaskDraftVO(BaseModel):
    """草案编号只在本次方案内有效，不是数据库任务 ID。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    draft_id: DraftId = Field(description="方案内唯一编号，T1 至 T12")
    title: str = Field(min_length=1, max_length=200, description="任务标题")
    description: str = Field(min_length=1, max_length=4000, description="任务说明")
    priority: int = Field(strict=True, ge=1, le=5, description="优先级，1 最高，5 最低")
    acceptance_criteria: str = Field(
        min_length=1, max_length=2000, description="可检查的任务验收标准"
    )
    dependencies: list[DraftId] = Field(
        max_length=11, description="本方案内的前置任务编号，不可使用数据库 ID"
    )
    source_ids: list[SourceId] = Field(
        max_length=12, description="依据的文档片段编号；没有直接依据时留空并说明假设"
    )

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("前置任务编号不能重复")
        if self.draft_id in self.dependencies:
            raise ValueError("任务不能依赖自身")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("文档引用编号不能重复")
        return self


class PlanProposalVO(BaseModel):
    """模型只能提出方案，不能指定用户、项目、审批结果或写入操作。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=2000, description="方案摘要")
    assumptions: list[PlanNote] = Field(max_length=8, description="需人工确认的假设")
    risks: list[PlanNote] = Field(max_length=8, description="实施风险与注意事项")
    tasks: list[TaskDraftVO] = Field(
        min_length=1, max_length=12, description="任务草案"
    )

    @model_validator(mode="after")
    def validate_tasks(self) -> Self:
        ids = {task.draft_id for task in self.tasks}
        if len(ids) != len(self.tasks):
            raise ValueError("任务草案编号不能重复")
        titles = {normalize_task_title(task.title) for task in self.tasks}
        if len(titles) != len(self.tasks):
            raise ValueError("任务标题不能重复")
        graph = {task.draft_id: task.dependencies for task in self.tasks}
        if any(
            dependency not in ids for items in graph.values() for dependency in items
        ):
            raise ValueError("前置任务必须引用本方案中存在的编号")
        visiting, visited = set(), set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("任务依赖不能形成循环")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in graph[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in graph:
            visit(task_id)
        return self


class ToolCallVO(BaseModel):
    name: Literal["search_documents", "read_task_board"]
    status: Literal["success", "empty"]
    item_count: int = Field(ge=0)


class PlanInfoVO(BaseModel):
    mode: Literal["mock", "live"]
    configured: bool
    ready_documents: int = Field(ge=0)
    task_count: int = Field(ge=0)


class PlanResultVO(BaseModel):
    mode: Literal["mock", "live"]
    proposal: PlanProposalVO
    sources: list[RagSourceVO]
    tool_calls: list[ToolCallVO]
    board_task_count: int = Field(ge=0)
    persisted: Literal[False] = False
