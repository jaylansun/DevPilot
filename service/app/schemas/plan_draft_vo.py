from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.plan_vo import PlanResultVO


class PlanDraftVO(BaseModel):
    id: UUID
    project_id: UUID
    goal: str
    plan: PlanResultVO
    version: int
    status: Literal["draft", "submitted"]
    conversation_id: UUID | None
    created_at: datetime
    updated_at: datetime


class PlanDraftPageVO(BaseModel):
    items: list[PlanDraftVO]
    total: int
    offset: int
    limit: int
