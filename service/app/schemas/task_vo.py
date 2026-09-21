from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.task_do import TaskSource, TaskStatus


class TaskVO(BaseModel):
    """返回给客户端的任务数据。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str
    description: str
    priority: int
    status: TaskStatus
    acceptance_criteria: str
    source: TaskSource
    approval_id: UUID | None = None
    dependency_ids: list[UUID] = Field(default_factory=list)
    version: int
    created_at: datetime
    updated_at: datetime


class TaskPageVO(BaseModel):
    """任务分页查询结果。"""

    items: list[TaskVO]
    total: int
    offset: int
    limit: int
