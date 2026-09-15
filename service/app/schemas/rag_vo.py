from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RagSourceVO(BaseModel):
    source_id: int = Field(ge=1, description="回答中的引用编号")
    document_id: UUID
    filename: str
    chunk_index: int = Field(ge=0, description="文档片段编号，从 0 开始")
    heading: str
    text: str = Field(max_length=400, description="服务器检索得到的原文片段")


class RagAnswerVO(BaseModel):
    answer: str
    sources: list[RagSourceVO]
    status: Literal["answered", "insufficient_evidence"]
    mode: Literal["mock", "live"]


class RagInfoVO(BaseModel):
    mode: Literal["mock", "live"]
    configured: bool
    ready_documents: int


class GroundedAnswerVO(BaseModel):
    """约束模型输出；文件名、片段正文等引用信息由服务器补齐。"""

    answer: str = Field(
        min_length=1,
        max_length=4000,
        description="中文回答，事实后用 [1] 等编号引用依据",
    )
    source_ids: list[int] = Field(
        max_length=4, description="实际使用的片段编号，不得编造"
    )
    insufficient_evidence: bool = Field(description="资料不能支持回答时必须为 true")
