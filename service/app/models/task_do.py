from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskSource(StrEnum):
    MANUAL = "manual"
    AI = "ai"


class TaskDO(Base):
    """项目任务；版本号用于检测并发编辑冲突。"""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "priority BETWEEN 1 AND 5",
            name="ck_tasks_priority",
        ),
        UniqueConstraint("project_id", "title", name="uq_tasks_project_title"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    project_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default="",
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger,
        default=3,
        server_default="3",
        nullable=False,
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_type: [value.value for value in enum_type],
        ),
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
        nullable=False,
    )
    acceptance_criteria: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default="",
        nullable=False,
    )
    source: Mapped[TaskSource] = mapped_column(
        Enum(
            TaskSource,
            name="task_source",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_type: [value.value for value in enum_type],
        ),
        default=TaskSource.MANUAL,
        server_default=TaskSource.MANUAL.value,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __mapper_args__ = {"version_id_col": version}
