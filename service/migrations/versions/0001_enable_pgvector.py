"""启用 PostgreSQL 的 pgvector 扩展。

版本号: 0001_pgvector
上一版本:
创建时间: 2026-09-09
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0001_pgvector"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # 降级时保留扩展及其向量数据；如需删除，应由数据库管理员显式操作。
    pass
