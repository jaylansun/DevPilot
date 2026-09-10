from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import DatabaseSession, MemberUser
from app.errors import ApiError
from app.schemas.project_qo import ProjectCreateQO, ProjectUpdateQO
from app.schemas.project_vo import ProjectPageVO, ProjectVO
from app.services.project_service import (
    ProjectNameAlreadyExistsError,
    ProjectNotFoundError,
    create_project as create_project_record,
    delete_project as delete_project_record,
    get_project as get_project_record,
    get_projects_page,
    update_project as update_project_record,
)


router = APIRouter(prefix="/projects", tags=["项目"])


def _project_not_found() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="project_not_found",
        message="项目不存在",
    )


def _project_name_conflict() -> ApiError:
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="project_name_exists",
        message="当前用户已经拥有同名项目",
    )


@router.post(
    "",
    response_model=ProjectVO,
    status_code=status.HTTP_201_CREATED,
    summary="创建项目",
)
async def create_project(
    payload: ProjectCreateQO,
    session: DatabaseSession,
    current_user: MemberUser,
) -> ProjectVO:
    try:
        project = await create_project_record(
            session,
            current_user.id,
            name=payload.name,
            description=payload.description,
        )
    except ProjectNameAlreadyExistsError as exc:
        raise _project_name_conflict() from exc
    return ProjectVO.model_validate(project)


@router.get("", response_model=ProjectPageVO, summary="分页查询我的项目")
async def list_projects(
    session: DatabaseSession,
    current_user: MemberUser,
    offset: Annotated[int, Query(ge=0, description="跳过的记录数")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="每页记录数")] = 20,
) -> ProjectPageVO:
    projects, total = await get_projects_page(
        session,
        current_user.id,
        offset=offset,
        limit=limit,
    )
    return ProjectPageVO(
        items=[ProjectVO.model_validate(project) for project in projects],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{project_id}", response_model=ProjectVO, summary="获取项目详情")
async def get_project(
    project_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
) -> ProjectVO:
    try:
        project = await get_project_record(session, current_user.id, project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    return ProjectVO.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectVO, summary="局部更新项目")
async def update_project(
    project_id: UUID,
    payload: ProjectUpdateQO,
    session: DatabaseSession,
    current_user: MemberUser,
) -> ProjectVO:
    try:
        project = await update_project_record(
            session,
            current_user.id,
            project_id,
            payload.model_dump(exclude_unset=True),
        )
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    except ProjectNameAlreadyExistsError as exc:
        raise _project_name_conflict() from exc
    return ProjectVO.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除项目",
)
async def delete_project(
    project_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
) -> Response:
    try:
        await delete_project_record(session, current_user.id, project_id)
    except ProjectNotFoundError as exc:
        raise _project_not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
