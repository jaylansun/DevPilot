from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.task_do import TaskStatus
from app.schemas.plan_vo import ToolCallVO
from app.schemas.rag_vo import RagSourceVO
from app.schemas.workflow_qo import WorkflowIntent

SourceId = Annotated[int, Field(strict=True, ge=1, le=4)]
Note = Annotated[str, Field(min_length=1, max_length=1000)]


class WorkflowIntentVO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    intent: WorkflowIntent


class RequirementEvidenceVO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    requirement: str = Field(min_length=1, max_length=500)
    explanation: Note
    source_ids: list[SourceId] = Field(min_length=1, max_length=4)


class CoveredRequirementVO(RequirementEvidenceVO):
    task_ids: list[UUID] = Field(min_length=1, max_length=100)


class RequirementQuestionVO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: Note
    reason: Note
    source_ids: list[SourceId] = Field(min_length=1, max_length=4)


class GapReportVO(BaseModel):
    """仅分析已读片段；允许没有遗漏，不输出可执行任务或审批字段。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=2000)
    covered: list[CoveredRequirementVO] = Field(max_length=20)
    missing: list[RequirementEvidenceVO] = Field(max_length=20)
    questions: list[RequirementQuestionVO] = Field(max_length=20)
    reviewed_source_ids: list[SourceId] = Field(min_length=1, max_length=4)
    insufficient_evidence: bool


class TaskLookupVO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    summary: str = Field(min_length=1, max_length=2000)
    task_ids: list[UUID] = Field(max_length=100)


class TaskEvidenceVO(BaseModel):
    id: UUID
    title: str
    status: TaskStatus
    priority: int
    description: str
    acceptance_criteria: str
    description_truncated: bool
    acceptance_criteria_truncated: bool


class DocumentScopeVO(BaseModel):
    document_id: UUID
    filename: str


class WorkflowScopeVO(BaseModel):
    ready_documents: list[DocumentScopeVO]
    retrieved_source_count: int = Field(ge=0)
    document_search_performed: bool
    full_document_review: Literal[False] = False
    board_read: bool
    tasks: list[TaskEvidenceVO]
    task_details_truncated: bool
    limitation: str


class WorkflowInfoVO(BaseModel):
    mode: Literal["mock", "live"]
    configured: bool
    ready_documents: int
    task_count: int


class WorkflowResultVO(BaseModel):
    intent: WorkflowIntent
    mode: Literal["mock", "live"]
    status: Literal[
        "reviewed", "answered", "insufficient_evidence", "demo", "clarification_needed"
    ]
    answer: str
    report: GapReportVO | None = None
    tasks: list[TaskEvidenceVO]
    sources: list[RagSourceVO]
    scope: WorkflowScopeVO
    tool_calls: list[ToolCallVO]
    persisted: Literal[False] = False
