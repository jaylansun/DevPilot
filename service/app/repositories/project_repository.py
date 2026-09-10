from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_do import ProjectDO


async def get_owned_project(
    session: AsyncSession,
    project_id: UUID,
    owner_id: UUID,
) -> ProjectDO | None:
    return await session.scalar(
        select(ProjectDO).where(
            ProjectDO.id == project_id,
            ProjectDO.owner_id == owner_id,
        )
    )


async def list_owned_projects(
    session: AsyncSession,
    owner_id: UUID,
    *,
    offset: int,
    limit: int,
) -> tuple[list[ProjectDO], int]:
    condition = ProjectDO.owner_id == owner_id
    total = int(
        await session.scalar(
            select(func.count(ProjectDO.id)).where(condition)
        )
        or 0
    )
    projects = list(
        await session.scalars(
            select(ProjectDO)
            .where(condition)
            .order_by(ProjectDO.created_at.desc(), ProjectDO.id)
            .offset(offset)
            .limit(limit)
        )
    )
    return projects, total
