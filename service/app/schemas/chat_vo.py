from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.plan_vo import ToolCallVO
from app.schemas.rag_vo import RagSourceVO
from app.schemas.workflow_vo import TaskEvidenceVO


class ChatInfoVO(BaseModel):
    mode: Literal["mock", "live"]
    configured: bool
    ready_documents: int = Field(ge=0)


class ChatAnswerVO(BaseModel):
    answer: str
    basis: Literal["general", "project"]
    sources: list[RagSourceVO]
    tasks: list[TaskEvidenceVO]
    tool_calls: list[ToolCallVO]
    status: Literal["answered", "insufficient_evidence", "demo"]
    mode: Literal["mock", "live"]


class ChatCompletion(BaseModel):
    """提交最终回答；项目事实必须来自本轮工具结果，通用回答不伪造引用。"""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    basis: Literal["general", "project"]
    source_ids: list[Annotated[int, Field(strict=True, ge=1, le=12)]] = Field(
        max_length=12, description="本轮实际使用的文档编号，正文用 [1] 等编号标注"
    )
    task_ids: list[UUID] = Field(max_length=100, description="本轮实际使用的任务 UUID")
    insufficient_evidence: bool
