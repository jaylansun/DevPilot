"""Enable the pgvector PostgreSQL extension.

Revision ID: 0001_pgvector
Revises:
Create Date: 2026-09-09
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
    # Keep the extension and its vector data during a downgrade. Removing it
    # later is an explicit database-administration operation.
    pass
