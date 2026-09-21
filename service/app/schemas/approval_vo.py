from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.approval_qo import ApprovalDecisionQO
from app.schemas.plan_vo import PlanResultVO

ApprovalStatus = Literal["pending", "processing", "approved", "rejected"]


class CreatedTaskVO(BaseModel):
    draft_id: str
    task_id: UUID
    title: str
    dependency_ids: list[UUID]


class ApprovalVO(BaseModel):
    id: UUID
    conversation_id: UUID
    project_id: UUID
    project_name: str
    goal: str
    status: ApprovalStatus
    plan: PlanResultVO
    decision: ApprovalDecisionQO | None
    reviewer_id: UUID | None
    created_tasks: list[CreatedTaskVO]
    created_at: datetime
    decided_at: datetime | None


class ApprovalPageVO(BaseModel):
    items: list[ApprovalVO]
    total: int
    offset: int
    limit: int


class ConversationVO(BaseModel):
    id: UUID
    project_id: UUID
    goal: str
    status: Literal[
        "new", "interrupted", "pending", "processing", "approved", "rejected"
    ]
    approval: ApprovalVO | None
