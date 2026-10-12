from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from app.schemas.plan_vo import PlanResultVO, ToolCallVO
from app.schemas.rag_vo import RagSourceVO
from app.schemas.workflow_vo import TaskEvidenceVO, WorkflowResultVO


class ChatPlanArtifactVO(BaseModel):
    """工件来源编号独立于聊天正文，草案只由会话提交事务保存。"""

    type: Literal["task_plan"] = "task_plan"
    goal: str = Field(min_length=1, max_length=2000)
    result: PlanResultVO
    draft_id: UUID | None = None
    draft_version: int | None = Field(default=None, ge=1)
    _document_hashes: dict = PrivateAttr(default_factory=dict)


class ChatCheckArtifactVO(BaseModel):
    type: Literal["requirement_check"] = "requirement_check"
    result: WorkflowResultVO


ChatArtifactVO = Annotated[
    ChatPlanArtifactVO | ChatCheckArtifactVO, Field(discriminator="type")
]


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
    artifacts: list[ChatArtifactVO] = Field(default_factory=list, max_length=2)
    _artifact_readers: list = PrivateAttr(default_factory=list)


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
