"""NDJSON v1：每行一个事件；final/error 是唯一终止事件。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.schemas.approval_vo import ApprovalVO
from app.schemas.error_vo import ErrorDetailVO
from app.schemas.plan_draft_vo import PlanDraftVO
from app.schemas.plan_vo import PlanResultVO
from app.schemas.rag_vo import RagAnswerVO
from app.schemas.workflow_vo import WorkflowResultVO

StepName = Literal[
    "retrieve_knowledge",
    "answer_knowledge",
    "validate_result",
    "classify_intent",
    "load_lookup_board",
    "answer_lookup",
    "retrieve_documents",
    "load_task_board",
    "generate_report",
    "clarify",
    "draft_proposal",
    "search_documents",
    "read_task_board",
    "submit_approval",
    "apply_approval",
]


class EventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    seq: int = Field(ge=1)
    request_id: str


class TokenEvent(EventBase):
    type: Literal["token"] = "token"
    text: str = Field(min_length=1, max_length=4000)


class NodeEvent(EventBase):
    type: Literal["node"] = "node"
    id: str
    name: StepName
    status: Literal["started", "completed", "failed"]


class ToolEvent(NodeEvent):
    type: Literal["tool"] = "tool"


class KnowledgeFinal(EventBase):
    type: Literal["final"] = "final"
    kind: Literal["knowledge"] = "knowledge"
    result: RagAnswerVO


class PlanningFinal(EventBase):
    type: Literal["final"] = "final"
    kind: Literal["planning"] = "planning"
    result: PlanResultVO


class WorkflowFinal(EventBase):
    type: Literal["final"] = "final"
    kind: Literal["workflow"] = "workflow"
    result: WorkflowResultVO


class DraftFinal(EventBase):
    type: Literal["final"] = "final"
    kind: Literal["draft"] = "draft"
    result: PlanDraftVO


class ApprovalRequiredEvent(EventBase):
    type: Literal["approval_required"] = "approval_required"
    approval: ApprovalVO


class ApprovalFinal(EventBase):
    type: Literal["final"] = "final"
    kind: Literal["approval"] = "approval"
    result: ApprovalVO


FinalEvent = Annotated[
    KnowledgeFinal | PlanningFinal | WorkflowFinal | ApprovalFinal | DraftFinal,
    Field(discriminator="kind"),
]


class ErrorEvent(EventBase):
    type: Literal["error"] = "error"
    status: int = Field(ge=400, le=599)
    error: ErrorDetailVO


StreamEvent = Annotated[
    TokenEvent
    | NodeEvent
    | ToolEvent
    | ApprovalRequiredEvent
    | FinalEvent
    | ErrorEvent,
    Field(discriminator="type"),
]
stream_event_adapter = TypeAdapter(StreamEvent)
