from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO, TaskStatus


async def get_owned_task(
    session: AsyncSession,
    project_id: UUID,
    task_id: UUID,
    owner_id: UUID,
) -> TaskDO | None:
    return await session.scalar(
        select(TaskDO)
        .join(ProjectDO, ProjectDO.id == TaskDO.project_id)
        .where(
            TaskDO.id == task_id,
            TaskDO.project_id == project_id,
            ProjectDO.owner_id == owner_id,
        )
    )


async def list_project_tasks(
    session: AsyncSession,
    project_id: UUID,
    *,
    offset: int,
    limit: int,
    task_status: TaskStatus | None,
    priority: int | None,
) -> tuple[list[TaskDO], int]:
    conditions = [TaskDO.project_id == project_id]
    if task_status is not None:
        conditions.append(TaskDO.status == task_status)
    if priority is not None:
        conditions.append(TaskDO.priority == priority)

    total = int(
        await session.scalar(
            select(func.count(TaskDO.id)).where(*conditions)
        )
        or 0
    )
    tasks = list(
        await session.scalars(
            select(TaskDO)
            .where(*conditions)
            .order_by(TaskDO.status, TaskDO.priority, TaskDO.created_at, TaskDO.id)
            .offset(offset)
            .limit(limit)
        )
    )
    return tasks, total
