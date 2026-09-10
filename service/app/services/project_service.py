from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_do import ProjectDO
from app.repositories.project_repository import get_owned_project, list_owned_projects


class ProjectNotFoundError(LookupError):
    """当前用户无权访问或项目不存在。"""


class ProjectNameAlreadyExistsError(ValueError):
    """当前用户已经拥有同名项目。"""


async def create_project(
    session: AsyncSession,
    owner_id: UUID,
    *,
    name: str,
    description: str,
) -> ProjectDO:
    project = ProjectDO(owner_id=owner_id, name=name, description=description)
    try:
        session.add(project)
        await session.flush()
        await session.refresh(project)
    except IntegrityError as exc:
        raise ProjectNameAlreadyExistsError("项目名称已存在") from exc
    return project


async def get_project(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
) -> ProjectDO:
    project = await get_owned_project(session, project_id, owner_id)
    if project is None:
        raise ProjectNotFoundError("项目不存在")
    return project


async def get_projects_page(
    session: AsyncSession,
    owner_id: UUID,
    *,
    offset: int,
    limit: int,
) -> tuple[list[ProjectDO], int]:
    return await list_owned_projects(
        session,
        owner_id,
        offset=offset,
        limit=limit,
    )


async def update_project(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    changes: dict[str, object],
) -> ProjectDO:
    try:
        project = await get_owned_project(session, project_id, owner_id)
        if project is None:
            raise ProjectNotFoundError("项目不存在")
        for field, value in changes.items():
            setattr(project, field, value)
        await session.flush()
        await session.refresh(project)
    except IntegrityError as exc:
        raise ProjectNameAlreadyExistsError("项目名称已存在") from exc
    return project


async def delete_project(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
) -> None:
    project = await get_owned_project(session, project_id, owner_id)
    if project is None:
        raise ProjectNotFoundError("项目不存在")
    await session.delete(project)
    await session.flush()
