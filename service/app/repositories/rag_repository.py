from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_do import DocumentDO, DocumentStatus


async def list_ready_documents(
    session: AsyncSession, project_id: UUID
) -> dict[UUID, str]:
    """只读取已就绪文档的 ID 和文件名，不加载整篇原文。"""
    rows = await session.execute(
        select(DocumentDO.id, DocumentDO.filename).where(
            DocumentDO.project_id == project_id,
            DocumentDO.status == DocumentStatus.READY,
        )
    )
    return {row.id: row.filename for row in rows}
