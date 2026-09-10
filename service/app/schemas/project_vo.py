from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectVO(BaseModel):
    """返回给客户端的项目数据。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class ProjectPageVO(BaseModel):
    """项目分页查询结果。"""

    items: list[ProjectVO]
    total: int
    offset: int
    limit: int
