"""普通会话与消息；上下文由 LangGraph 检查点保存。"""

import sqlalchemy as sa
from alembic import op

revision = "0007_chat_sessions"
down_revision = "0006_plan_drafts"
branch_labels = None
depends_on = None


def fk(name, target, nullable=False, ondelete="CASCADE", **kwargs):
    return sa.Column(
        name,
        sa.Uuid(),
        sa.ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        **kwargs,
    )


def timestamp(name):
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade():
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        fk("owner_id", "users.id"),
        fk("project_id", "projects.id"),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("next_seq", sa.Integer(), nullable=False),
        sa.Column("checkpoint_id", sa.String(64), nullable=True),
        sa.Column("active_message_id", sa.Uuid(), nullable=True),
        sa.Column("busy_until", sa.DateTime(timezone=True), nullable=True),
        timestamp("created_at"),
        timestamp("updated_at"),
    )
    op.create_index(
        "ix_chat_sessions_owner_project",
        "chat_sessions",
        ["owner_id", "project_id", "updated_at"],
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        fk("session_id", "chat_sessions.id"),
        sa.Column("client_message_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Uuid(), nullable=False),
        timestamp("created_at"),
        sa.UniqueConstraint(
            "session_id", "client_message_id", name="uq_chat_message_client"
        ),
        sa.UniqueConstraint("session_id", "seq", name="uq_chat_message_seq"),
    )


def downgrade():
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_owner_project", table_name="chat_sessions")
    op.drop_table("chat_sessions")
