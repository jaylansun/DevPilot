from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import DatabaseSession, MemberUser
from app.schemas.plan_qo import PlanRequestQO
from app.schemas.plan_vo import PlanInfoVO, PlanResultVO
from app.services.document_service import require_document_project
from app.services.plan_service import PlanService
from app.services.run_stream_service import NDJSONResponse, stream_response

router = APIRouter(prefix="/projects/{project_id}/planning", tags=["任务规划"])


def get_plan_service(request: Request) -> PlanService:
    return request.app.state.plan_service


PlanDependency = Annotated[PlanService, Depends(get_plan_service)]


@router.get("", response_model=PlanInfoVO, summary="读取任务规划模式与资料状态")
async def planning_info(
    project_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
    planner: PlanDependency,
):
    return await planner.info(session, current_user.id, project_id)


@router.post(
    "/proposals", response_model=PlanResultVO, summary="生成只读任务草案，不写入看板"
)
async def create_proposal(
    project_id: UUID,
    body: PlanRequestQO,
    current_user: MemberUser,
    planner: PlanDependency,
):
    return await planner.create(current_user.id, project_id, body.goal)


@router.post(
    "/proposals/stream",
    response_class=NDJSONResponse,
    summary="流式任务规划：NDJSON v1 事件",
)
async def stream_proposal(
    project_id: UUID,
    body: PlanRequestQO,
    request: Request,
    current_user: MemberUser,
    planner: PlanDependency,
):
    async with planner.session_factory() as session:
        await require_document_project(session, current_user.id, project_id)
    return stream_response(
        lambda events: planner.create(
            current_user.id, project_id, body.goal, events=events
        ),
        "planning",
        request.state.request_id,
    )
