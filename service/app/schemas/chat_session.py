from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chat_vo import ChatAnswerVO


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SessionMessageQO(StrictInput):
    question: str = Field(min_length=1, max_length=2000)
    client_message_id: UUID


class SessionVO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class SavedMessageVO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    client_message_id: UUID
    seq: int
    question: str
    answer: ChatAnswerVO | None
    status: Literal["pending", "completed", "failed", "cancelled"]
    error: str | None
    created_at: datetime


class SessionDetailVO(BaseModel):
    session: SessionVO
    messages: list[SavedMessageVO]
    has_more: bool
