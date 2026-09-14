from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"
    DELETE_FAILED = "delete_failed"


class DocumentDO(Base):
    """原文和后台任务状态保存在数据库中，重启后可继续处理。"""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "content_hash", name="uq_documents_project_hash"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            values_callable=lambda values: [v.value for v in values],
            native_enum=False,
            create_constraint=True,
            name="document_status",
        ),
        default=DocumentStatus.QUEUED,
        server_default="queued",
        nullable=False,
        index=True,
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
