from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.user_do import UserRole


class UserVO(BaseModel):
    """返回给客户端的用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    role: UserRole
    created_at: datetime
    updated_at: datetime


class TokenVO(BaseModel):
    """登录成功后返回的访问令牌。"""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserVO
