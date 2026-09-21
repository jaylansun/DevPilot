"""增加持久规划会话、审批执行记录和 AI 任务来源关联。"""

import sqlalchemy as sa
from alembic import op

revision = "0005_approvals"
down_revision = "0004_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thread_id", sa.String(36), nullable=False, unique=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("execution_key", sa.Uuid(), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("document_hashes", sa.JSON(), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=True),
        sa.Column(
            "reviewer_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_tasks", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'approved', 'rejected')",
            name="ck_approvals_status",
        ),
    )
    op.create_index("ix_approvals_status", "approvals", ["status"])
    op.add_column(
        "tasks",
        sa.Column(
            "approval_id",
            sa.Uuid(),
            sa.ForeignKey("approvals.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("tasks", sa.Column("draft_id", sa.String(3), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("dependency_ids", sa.JSON(), server_default="[]", nullable=False),
    )
    op.create_unique_constraint(
        "uq_tasks_approval_draft", "tasks", ["approval_id", "draft_id"]
    )


def downgrade():
    op.drop_constraint("uq_tasks_approval_draft", "tasks", type_="unique")
    op.drop_column("tasks", "dependency_ids")
    op.drop_column("tasks", "draft_id")
    op.drop_column("tasks", "approval_id")
    op.drop_table("approvals")
    op.drop_table("conversations")
