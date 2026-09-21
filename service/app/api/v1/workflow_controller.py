from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import DatabaseSession, MemberUser
from app.schemas.workflow_qo import WorkflowRequestQO
from app.schemas.workflow_vo import WorkflowInfoVO, WorkflowResultVO
from app.services.document_service import require_document_project
from app.services.run_stream_service import NDJSONResponse, stream_response
from app.services.workflow_service import WorkflowService

router = APIRouter(
    prefix="/projects/{project_id}/assistant", tags=["需求检查与项目助手"]
)


def get_workflow_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


WorkflowDependency = Annotated[WorkflowService, Depends(get_workflow_service)]


@router.get("", response_model=WorkflowInfoVO, summary="读取项目助手状态")
async def workflow_info(
    project_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
    workflow: WorkflowDependency,
):
    return await workflow.info(session, current_user.id, project_id)


@router.post(
    "/runs", response_model=WorkflowResultVO, summary="只读需求检查、文档问答或任务查询"
)
async def run_workflow(
    project_id: UUID,
    body: WorkflowRequestQO,
    session: DatabaseSession,
    current_user: MemberUser,
    workflow: WorkflowDependency,
):
    return await workflow.run(session, current_user.id, project_id, body)


@router.post(
    "/runs/stream",
    response_class=NDJSONResponse,
    summary="流式需求检查：NDJSON v1 事件",
)
async def stream_workflow(
    project_id: UUID,
    body: WorkflowRequestQO,
    request: Request,
    session: DatabaseSession,
    current_user: MemberUser,
    workflow: WorkflowDependency,
):
    await require_document_project(session, current_user.id, project_id)
    return stream_response(
        lambda events: workflow.run(
            session,
            current_user.id,
            project_id,
            body,
            events=events,
            streaming=True,
        ),
        "workflow",
        request.state.request_id,
    )
