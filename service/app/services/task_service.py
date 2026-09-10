from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO, TaskSource, TaskStatus
from app.repositories.project_repository import get_owned_project
from app.repositories.task_repository import get_owned_task, list_project_tasks


class TaskNotFoundError(LookupError):
    """当前用户无权访问或任务不存在。"""


class TaskTitleAlreadyExistsError(ValueError):
    """当前项目已经存在同标题任务。"""


class TaskVersionConflictError(ValueError):
    """任务已经被其他请求修改。"""


async def _require_project(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
) -> ProjectDO:
    project = await get_owned_project(session, project_id, owner_id)
    if project is None:
        raise TaskNotFoundError("项目不存在")
    return project


async def create_task(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    *,
    title: str,
    description: str,
    priority: int,
    task_status: TaskStatus,
    acceptance_criteria: str,
) -> TaskDO:
    try:
        await _require_project(session, owner_id, project_id)
        task = TaskDO(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            status=task_status,
            acceptance_criteria=acceptance_criteria,
            source=TaskSource.MANUAL,
        )
        session.add(task)
        await session.flush()
        await session.refresh(task)
    except IntegrityError as exc:
        raise TaskTitleAlreadyExistsError("任务标题已存在") from exc
    return task


async def get_task(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    task_id: UUID,
) -> TaskDO:
    task = await get_owned_task(session, project_id, task_id, owner_id)
    if task is None:
        raise TaskNotFoundError("任务不存在")
    return task


async def get_tasks_page(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    *,
    offset: int,
    limit: int,
    task_status: TaskStatus | None,
    priority: int | None,
) -> tuple[list[TaskDO], int]:
    await _require_project(session, owner_id, project_id)
    return await list_project_tasks(
        session,
        project_id,
        offset=offset,
        limit=limit,
        task_status=task_status,
        priority=priority,
    )


async def update_task(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    task_id: UUID,
    *,
    expected_version: int,
    changes: dict[str, object],
) -> TaskDO:
    try:
        task = await get_owned_task(session, project_id, task_id, owner_id)
        if task is None:
            raise TaskNotFoundError("任务不存在")
        if task.version != expected_version:
            raise TaskVersionConflictError("任务版本已经发生变化")
        for field, value in changes.items():
            setattr(task, field, value)
        await session.flush()
        await session.refresh(task)
    except IntegrityError as exc:
        raise TaskTitleAlreadyExistsError("任务标题已存在") from exc
    except StaleDataError as exc:
        raise TaskVersionConflictError("任务版本已经发生变化") from exc
    return task


async def delete_task(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    task_id: UUID,
) -> None:
    try:
        task = await get_owned_task(session, project_id, task_id, owner_id)
        if task is None:
            raise TaskNotFoundError("任务不存在")
        await session.delete(task)
        await session.flush()
    except StaleDataError as exc:
        raise TaskVersionConflictError("任务已经被其他请求修改") from exc
