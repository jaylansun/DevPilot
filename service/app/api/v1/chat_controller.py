from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.dependencies import DatabaseSession, MemberUser
from app.schemas.chat_qo import ChatRequestQO
from app.schemas.chat_session import (
    SessionDetailVO,
    SessionMessageQO,
    SessionVO,
)
from app.schemas.chat_vo import ChatAnswerVO, ChatInfoVO
from app.services.chat_service import ChatService
from app.services.chat_session_service import ChatSessionService
from app.services.run_stream_service import NDJSONResponse, stream_response

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["项目聊天"])


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


ChatDependency = Annotated[ChatService, Depends(get_chat_service)]


@router.get("", response_model=ChatInfoVO, summary="读取聊天模型与项目资料状态")
async def chat_info(
    project_id: UUID, session: DatabaseSession, user: MemberUser, chat: ChatDependency
):
    return await chat.info(session, user.id, project_id)


@router.post(
    "/messages", response_model=ChatAnswerVO, summary="自然聊天，按需检索项目资料和任务"
)
async def chat_message(
    project_id: UUID, body: ChatRequestQO, user: MemberUser, chat: ChatDependency
):
    return await chat.answer(user.id, project_id, body)


@router.post(
    "/messages/stream", response_class=NDJSONResponse, summary="流式聊天与工具调用进度"
)
async def stream_chat(
    project_id: UUID,
    body: ChatRequestQO,
    request: Request,
    user: MemberUser,
    chat: ChatDependency,
):
    await chat.authorize(user.id, project_id)
    return stream_response(
        lambda events: chat.answer(
            user.id, project_id, body, events=events, streaming=True
        ),
        "chat",
        request.state.request_id,
    )


def get_chat_sessions(request: Request) -> ChatSessionService:
    return request.app.state.chat_sessions


SessionsDependency = Annotated[ChatSessionService, Depends(get_chat_sessions)]


@router.get(
    "/sessions", response_model=list[SessionVO], summary="我的项目会话，每页50条"
)
async def list_sessions(
    project_id: UUID,
    user: MemberUser,
    service: SessionsDependency,
    offset: int = Query(0, ge=0),
):
    return await service.list(user.id, project_id, offset)


@router.post(
    "/sessions", response_model=SessionVO, status_code=201, summary="新建普通会话"
)
async def create_session(
    project_id: UUID, user: MemberUser, service: SessionsDependency
):
    return await service.create(user.id, project_id)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailVO,
    summary="读取会话和最近40轮，支持向前翻页",
)
async def get_session(
    project_id: UUID,
    session_id: UUID,
    user: MemberUser,
    service: SessionsDependency,
    before: int | None = Query(None, ge=1),
):
    return await service.get(user.id, project_id, session_id, before)


@router.delete("/sessions/{session_id}", status_code=204, summary="删除会话及其上下文")
async def delete_session(
    project_id: UUID, session_id: UUID, user: MemberUser, service: SessionsDependency
):
    await service.delete(user.id, project_id, session_id)
    return Response(status_code=204)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatAnswerVO,
    summary="保存问答并加载当前会话上下文",
)
async def saved_chat(
    project_id: UUID,
    session_id: UUID,
    body: SessionMessageQO,
    user: MemberUser,
    service: SessionsDependency,
):
    return await service.answer(user.id, project_id, session_id, body)


@router.post(
    "/sessions/{session_id}/messages/stream",
    response_class=NDJSONResponse,
    summary="保存问答并流式输出",
)
async def saved_chat_stream(
    project_id: UUID,
    session_id: UUID,
    body: SessionMessageQO,
    request: Request,
    user: MemberUser,
    service: SessionsDependency,
):
    await service.authorize(user.id, project_id, session_id)
    return stream_response(
        lambda events: service.answer(
            user.id, project_id, session_id, body, events=events, streaming=True
        ),
        "chat",
        request.state.request_id,
    )
