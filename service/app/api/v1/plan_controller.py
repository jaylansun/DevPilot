from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import DatabaseSession, MemberUser
from app.schemas.plan_qo import PlanRequestQO
from app.schemas.plan_vo import PlanInfoVO, PlanResultVO
from app.services.plan_service import PlanService

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
    session: DatabaseSession,
    current_user: MemberUser,
    planner: PlanDependency,
):
    return await planner.create(session, current_user.id, project_id, body.goal)
