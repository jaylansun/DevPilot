from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import DatabaseSession, MemberUser
from app.schemas.rag_qo import RagQuestionQO
from app.schemas.rag_vo import RagAnswerVO, RagInfoVO
from app.services.document_service import require_document_project
from app.services.rag_service import RagService
from app.services.run_stream_service import NDJSONResponse, stream_response

router = APIRouter(prefix="/projects/{project_id}/knowledge", tags=["知识库问答"])


def get_rag_service(request: Request) -> RagService:
    return request.app.state.rag_service


RagDependency = Annotated[RagService, Depends(get_rag_service)]


@router.get("", response_model=RagInfoVO, summary="读取问答模式与知识库就绪状态")
async def knowledge_info(
    project_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
    rag: RagDependency,
):
    return await rag.info(session, current_user.id, project_id)


@router.post(
    "/questions",
    response_model=RagAnswerVO,
    summary="根据项目文档回答单轮问题并返回来源",
)
async def ask_question(
    project_id: UUID,
    body: RagQuestionQO,
    current_user: MemberUser,
    rag: RagDependency,
):
    return await rag.answer(current_user.id, project_id, body.question)


@router.post(
    "/questions/stream",
    response_class=NDJSONResponse,
    summary="流式知识问答：NDJSON v1 事件",
)
async def stream_question(
    project_id: UUID,
    body: RagQuestionQO,
    request: Request,
    current_user: MemberUser,
    rag: RagDependency,
):
    async with rag.session_factory() as session:
        await require_document_project(session, current_user.id, project_id)
    return stream_response(
        lambda events: rag.answer(
            current_user.id,
            project_id,
            body.question,
            events=events,
            streaming=True,
        ),
        "knowledge",
        request.state.request_id,
    )
