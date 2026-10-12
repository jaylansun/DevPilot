"""统一项目助手的本轮用途；旧会话默认自动选择。"""

import sqlalchemy as sa
from alembic import op

revision = "0008_unified_assistant"
down_revision = "0007_chat_sessions"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("chat_messages") as batch:
        batch.add_column(
            sa.Column("intent", sa.String(24), server_default="auto", nullable=False)
        )
        batch.create_check_constraint(
            "ck_chat_message_intent",
            "intent IN ('auto', 'task_planning', 'requirement_check')",
        )


def downgrade():
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_constraint("ck_chat_message_intent", type_="check")
        batch.drop_column("intent")
