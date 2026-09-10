from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import DatabaseSession, MemberUser
from app.errors import ApiError
from app.models.task_do import TaskStatus
from app.schemas.task_qo import TaskCreateQO, TaskUpdateQO
from app.schemas.task_vo import TaskPageVO, TaskVO
from app.services.task_service import (
    TaskNotFoundError,
    TaskTitleAlreadyExistsError,
    TaskVersionConflictError,
    create_task as create_task_record,
    delete_task as delete_task_record,
    get_task as get_task_record,
    get_tasks_page,
    update_task as update_task_record,
)


router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["任务"])


def _resource_not_found(message: str = "任务不存在") -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="task_or_project_not_found",
        message=message,
    )


def _task_title_conflict() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="task_title_exists",
        message="当前项目已经存在同标题任务",
    )


def _task_version_conflict() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="task_version_conflict",
        message="任务已经被其他请求修改，请刷新后重试",
    )


@router.post(
    "",
    response_model=TaskVO,
    status_code=status.HTTP_201_CREATED,
    summary="手工创建任务",
)
async def create_task(
    project_id: UUID,
    payload: TaskCreateQO,
    session: DatabaseSession,
    current_user: MemberUser,
) -> TaskVO:
    try:
        task = await create_task_record(
            session,
            current_user.id,
            project_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            task_status=payload.status,
            acceptance_criteria=payload.acceptance_criteria,
        )
    except TaskNotFoundError as exc:
        raise _resource_not_found(str(exc)) from exc
    except TaskTitleAlreadyExistsError as exc:
        raise _task_title_conflict() from exc
    return TaskVO.model_validate(task)


@router.get("", response_model=TaskPageVO, summary="分页查询项目任务")
async def list_tasks(
    project_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
    offset: Annotated[int, Query(ge=0, description="跳过的记录数")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="每页记录数")] = 20,
    task_status: Annotated[
        TaskStatus | None,
        Query(alias="status", description="按任务状态筛选"),
    ] = None,
    priority: Annotated[
        int | None,
        Query(ge=1, le=5, description="按优先级筛选"),
    ] = None,
) -> TaskPageVO:
    try:
        tasks, total = await get_tasks_page(
            session,
            current_user.id,
            project_id,
            offset=offset,
            limit=limit,
            task_status=task_status,
            priority=priority,
        )
    except TaskNotFoundError as exc:
        raise _resource_not_found(str(exc)) from exc
    return TaskPageVO(
        items=[TaskVO.model_validate(task) for task in tasks],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{task_id}", response_model=TaskVO, summary="获取任务详情")
async def get_task(
    project_id: UUID,
    task_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
) -> TaskVO:
    try:
        task = await get_task_record(session, current_user.id, project_id, task_id)
    except TaskNotFoundError as exc:
        raise _resource_not_found() from exc
    return TaskVO.model_validate(task)


@router.patch("/{task_id}", response_model=TaskVO, summary="局部更新任务")
async def update_task(
    project_id: UUID,
    task_id: UUID,
    payload: TaskUpdateQO,
    session: DatabaseSession,
    current_user: MemberUser,
) -> TaskVO:
    changes = payload.model_dump(exclude={"version"}, exclude_unset=True)
    try:
        task = await update_task_record(
            session,
            current_user.id,
            project_id,
            task_id,
            expected_version=payload.version,
            changes=changes,
        )
    except TaskNotFoundError as exc:
        raise _resource_not_found() from exc
    except TaskTitleAlreadyExistsError as exc:
        raise _task_title_conflict() from exc
    except TaskVersionConflictError as exc:
        raise _task_version_conflict() from exc
    return TaskVO.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除任务",
)
async def delete_task(
    project_id: UUID,
    task_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
) -> Response:
    try:
        await delete_task_record(session, current_user.id, project_id, task_id)
    except TaskNotFoundError as exc:
        raise _resource_not_found() from exc
    except TaskVersionConflictError as exc:
        raise _task_version_conflict() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
