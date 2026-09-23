from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanDraftDO(Base):
    """服务端保存的规划内容；送审绑定后不可变，版本号只随内容编辑递增。"""

    __tablename__ = "plan_drafts"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_plan_drafts_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    goal: Mapped[str] = mapped_column(Text)
    plan: Mapped[dict] = mapped_column(JSON)
    document_hashes: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __mapper_args__: ClassVar[dict] = {
        "version_id_col": version,
        "version_id_generator": False,
    }
