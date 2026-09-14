from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.document_do import DocumentDO


async def list_project_documents(
    session: AsyncSession, project_id: UUID
) -> list[DocumentDO]:
    return list(
        await session.scalars(
            select(DocumentDO)
            .options(defer(DocumentDO.content))
            .where(DocumentDO.project_id == project_id)
            .order_by(DocumentDO.created_at.desc(), DocumentDO.id)
        )
    )


async def get_project_document(
    session: AsyncSession,
    project_id: UUID,
    document_id: UUID,
) -> DocumentDO | None:
    return await session.scalar(
        select(DocumentDO).where(
            DocumentDO.id == document_id,
            DocumentDO.project_id == project_id,
        )
    )
