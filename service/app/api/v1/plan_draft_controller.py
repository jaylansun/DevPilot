from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import MemberUser
from app.schemas.plan_draft_qo import DraftSubmitQO, DraftUpdateQO
from app.schemas.plan_draft_vo import PlanDraftPageVO, PlanDraftVO
from app.schemas.plan_qo import PlanRequestQO
from app.services.document_service import require_document_project
from app.services.plan_draft_service import PlanDraftService
from app.services.run_stream_service import NDJSONResponse, stream_response

router = APIRouter(prefix="/projects/{project_id}/planning/drafts", tags=["规划草案"])


def get_draft_service(request: Request) -> PlanDraftService:
    return request.app.state.plan_draft_service


DraftDependency = Annotated[PlanDraftService, Depends(get_draft_service)]


@router.post("/stream", response_class=NDJSONResponse, summary="生成并保存规划草案")
async def generate_draft(
    project_id: UUID,
    body: PlanRequestQO,
    request: Request,
    user: MemberUser,
    service: DraftDependency,
):
    async with service.sessions() as session:
        await require_document_project(session, user.id, project_id)
    return stream_response(
        lambda events: service.generate(user, project_id, body.goal, events=events),
        "draft",
        request.state.request_id,
    )


@router.get("", response_model=PlanDraftPageVO, summary="分页读取已保存草案")
async def list_drafts(
    project_id: UUID,
    user: MemberUser,
    service: DraftDependency,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
):
    return await service.list(user, project_id, offset, limit)


@router.get("/{draft_id}", response_model=PlanDraftVO, summary="读取草案及保存版本")
async def get_draft(
    project_id: UUID, draft_id: UUID, user: MemberUser, service: DraftDependency
):
    return await service.get(user, project_id, draft_id)


@router.patch("/{draft_id}", response_model=PlanDraftVO, summary="按版本保存草案编辑")
async def update_draft(
    project_id: UUID,
    draft_id: UUID,
    body: DraftUpdateQO,
    user: MemberUser,
    service: DraftDependency,
):
    return await service.update(user, project_id, draft_id, body)


@router.post(
    "/{draft_id}/submit/stream",
    response_class=NDJSONResponse,
    summary="将已保存版本直接送审，不重新生成",
)
async def submit_draft(
    project_id: UUID,
    draft_id: UUID,
    body: DraftSubmitQO,
    request: Request,
    user: MemberUser,
    service: DraftDependency,
):
    await service.get(user, project_id, draft_id)
    return stream_response(
        lambda events: service.submit(user, project_id, draft_id, body, events=events),
        "approval",
        request.state.request_id,
    )
