from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import CurrentUser, MemberUser, ReviewerUser
from app.schemas.approval_qo import ApprovalDecisionQO, ConversationCreateQO
from app.schemas.approval_vo import (
    ApprovalPageVO,
    ApprovalStatus,
    ApprovalVO,
    ConversationVO,
)
from app.services.approval_service import ApprovalService
from app.services.run_stream_service import NDJSONResponse, stream_response

router = APIRouter(tags=["规划会话与审批"])


def get_approval_service(request: Request) -> ApprovalService:
    return request.app.state.approval_service


ApprovalDependency = Annotated[ApprovalService, Depends(get_approval_service)]


@router.post(
    "/projects/{project_id}/conversations",
    response_model=ConversationVO,
    status_code=201,
)
async def create_conversation(
    project_id: UUID,
    body: ConversationCreateQO,
    user: MemberUser,
    service: ApprovalDependency,
):
    return await service.create(user, project_id, body.goal)


@router.get("/projects/{project_id}/conversations", response_model=list[ConversationVO])
async def list_conversations(
    project_id: UUID,
    user: MemberUser,
    service: ApprovalDependency,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
):
    return await service.conversations(user, project_id, offset, limit)


@router.get("/conversations/{conversation_id}", response_model=ConversationVO)
async def get_conversation(
    conversation_id: UUID, user: CurrentUser, service: ApprovalDependency
):
    return await service.get(user, conversation_id)


@router.post(
    "/conversations/{conversation_id}/runs/stream", response_class=NDJSONResponse
)
async def run_conversation(
    conversation_id: UUID,
    request: Request,
    user: MemberUser,
    service: ApprovalDependency,
):
    await service.get(user, conversation_id)
    return stream_response(
        lambda events: service.start(user, conversation_id, events=events),
        "approval",
        request.state.request_id,
    )


@router.get("/approvals", response_model=ApprovalPageVO)
async def list_approvals(
    user: CurrentUser,
    service: ApprovalDependency,
    status: ApprovalStatus | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
):
    return await service.list_approvals(user, status, offset, limit)


@router.get("/approvals/{approval_id}", response_model=ApprovalVO)
async def get_approval(
    approval_id: UUID, user: CurrentUser, service: ApprovalDependency
):
    return await service.get_approval(user, approval_id)


@router.post("/approvals/{approval_id}/decide/stream", response_class=NDJSONResponse)
async def decide_approval(
    approval_id: UUID,
    body: ApprovalDecisionQO,
    request: Request,
    user: ReviewerUser,
    service: ApprovalDependency,
):
    await service.get_approval(user, approval_id)
    return stream_response(
        lambda events: service.decide(user, approval_id, body, events=events),
        "approval",
        request.state.request_id,
    )
