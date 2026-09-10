"""创建项目表和任务表。

版本号: 0003_projects_tasks
上一版本: 0002_users
创建时间: 2026-09-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_projects_tasks"
down_revision: str | Sequence[str] | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_projects_owner_name"),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default="3", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "todo",
                "in_progress",
                "done",
                name="task_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="todo",
            nullable=False,
        ),
        sa.Column(
            "acceptance_criteria",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                "ai",
                name="task_source",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 5", name="ck_tasks_priority"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "title", name="uq_tasks_project_title"),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_table("projects")
