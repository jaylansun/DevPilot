from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole


class UsernameRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9_.-]+$",
        description="登录用户名，只能包含小写字母、数字、下划线、点和短横线",
    )

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().casefold()
        return value


class RegisterRequest(UsernameRequest):
    password: str = Field(
        min_length=8,
        max_length=128,
        description="登录密码，长度为 8 至 128 个字符",
    )


class LoginRequest(UsernameRequest):
    password: str = Field(
        min_length=1,
        max_length=128,
        description="登录密码",
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    role: UserRole
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserResponse
