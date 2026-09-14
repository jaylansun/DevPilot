from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.document_do import DocumentStatus


class DocumentVO(BaseModel):
    """不把原文、服务器路径或底层异常暴露给列表接口。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    filename: str
    size_bytes: int
    status: DocumentStatus
    chunk_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentListVO(BaseModel):
    items: list[DocumentVO]
    total: int
    max_documents: int = 20
    max_size_bytes: int = 2 * 1024 * 1024
