import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from openai import APITimeoutError
from sqlalchemy import delete, select

from app.errors import ApiError
from app.models.chat_do import (
    ChatMessageDO,
    ChatSessionDO,
)
from app.schemas.chat_qo import ChatRequestQO
from app.schemas.chat_session import SavedMessageVO, SessionDetailVO, SessionVO
from app.schemas.chat_vo import ChatAnswerVO
from app.services.chat_model_service import ChatThread
from app.services.document_service import require_document_project
from app.services.run_events import NOOP_EVENTS

logger = logging.getLogger(__name__)


def now():
    return datetime.now(UTC)


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class ChatSessionService:
    def __init__(self, factory, chat):
        self.factory, self.chat = factory, chat

    async def require(self, db, owner, project, session_id, *, lock=False):
        await require_document_project(db, owner, project)
        query = select(ChatSessionDO).where(
            ChatSessionDO.id == session_id,
            ChatSessionDO.owner_id == owner,
            ChatSessionDO.project_id == project,
        )
        row = await db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise ApiError(404, "chat_session_not_found", "会话不存在")
        return row

    async def authorize(self, owner, project, session_id):
        async with self.factory() as db:
            await self.require(db, owner, project, session_id)

    async def create(self, owner, project):
        async with self.factory.begin() as db:
            await require_document_project(db, owner, project)
            row = ChatSessionDO(owner_id=owner, project_id=project)
            db.add(row)
            await db.flush()
            return SessionVO.model_validate(row)

    async def list(self, owner, project, offset=0):
        async with self.factory() as db:
            await require_document_project(db, owner, project)
            rows = await db.scalars(
                select(ChatSessionDO)
                .where(
                    ChatSessionDO.owner_id == owner, ChatSessionDO.project_id == project
                )
                .order_by(ChatSessionDO.updated_at.desc(), ChatSessionDO.id)
                .offset(offset)
                .limit(50)
            )
            return [SessionVO.model_validate(row) for row in rows]

    async def recover(self, db, row):
        if row.active_message_id and (
            not row.busy_until or aware(row.busy_until) <= now()
        ):
            message = await db.get(ChatMessageDO, row.active_message_id)
            if message and message.status == "pending":
                message.status, message.error = (
                    "failed",
                    "上次处理已中断，可重试最后一条问题",
                )
            row.active_message_id, row.busy_until = None, None

    async def get(self, owner, project, session_id, before=None):
        async with self.factory.begin() as db:
            row = await self.require(db, owner, project, session_id, lock=True)
            await self.recover(db, row)
            await db.flush()
            query = select(ChatMessageDO).where(ChatMessageDO.session_id == session_id)
            if before is not None:
                query = query.where(ChatMessageDO.seq < before)
            messages = list(
                (
                    await db.scalars(query.order_by(ChatMessageDO.seq.desc()).limit(41))
                ).all()
            )
            return SessionDetailVO(
                session=SessionVO.model_validate(row),
                messages=[
                    SavedMessageVO.model_validate(m) for m in reversed(messages[:40])
                ],
                has_more=len(messages) > 40,
            )

    async def delete(self, owner, project, session_id):
        async with self.factory.begin() as db:
            row = await self.require(db, owner, project, session_id, lock=True)
            await self.recover(db, row)
            if row.active_message_id:
                raise ApiError(
                    409, "chat_session_busy", "此会话仍在回答，请结束后再删除"
                )
            # 检查点删除使用官方 API；会话行锁阻止删除期间开始新一轮。
            await self.chat.model_service.delete_thread(f"chat:{session_id}")
            await db.execute(
                delete(ChatMessageDO).where(ChatMessageDO.session_id == session_id)
            )
            await db.delete(row)

    async def start(self, owner, project, session_id, body):
        async with self.factory.begin() as db:
            row = await self.require(db, owner, project, session_id, lock=True)
            await self.recover(db, row)
            message = await db.scalar(
                select(ChatMessageDO).where(
                    ChatMessageDO.session_id == session_id,
                    ChatMessageDO.client_message_id == body.client_message_id,
                )
            )
            if message and message.question != body.question:
                raise ApiError(
                    409, "message_id_conflict", "相同消息编号不能用于不同问题"
                )
            if message and message.status == "completed":
                return (
                    message,
                    row.checkpoint_id,
                    ChatAnswerVO.model_validate(message.answer),
                )
            if row.active_message_id:
                raise ApiError(
                    409,
                    "chat_session_busy",
                    "此会话仍在处理上一条问题，请稍后刷新或重试",
                )
            if message and message.seq != row.next_seq - 1:
                raise ApiError(
                    409,
                    "chat_retry_outdated",
                    "只能原位重试最后一条问题；请作为新问题发送",
                )
            if not message:
                message = ChatMessageDO(
                    session_id=session_id,
                    client_message_id=body.client_message_id,
                    seq=row.next_seq,
                    question=body.question,
                    created_at=now(),
                )
                db.add(message)
                row.next_seq += 1
                if message.seq == 1:
                    row.title = body.question[:80]
            message.status, message.error, message.attempt = "pending", None, uuid4()
            await db.flush()
            row.active_message_id = message.id
            row.busy_until = now() + timedelta(seconds=120)
            row.updated_at = now()
            return message, row.checkpoint_id, None

    async def finish(self, owner, project, session_id, message, result, checkpoint_id):
        async with self.factory.begin() as db:
            row = await self.require(db, owner, project, session_id, lock=True)
            current = await db.get(ChatMessageDO, message.id)
            if (
                not current
                or current.attempt != message.attempt
                or row.active_message_id != message.id
            ):
                raise ApiError(
                    409, "chat_attempt_expired", "本次处理已失效，请刷新会话"
                )
            current.answer = result.model_dump(mode="json")
            current.status, current.error = "completed", None
            # 仅成功答案对应的检查点可供下一轮读取；失败的图状态不会串入历史。
            row.checkpoint_id = checkpoint_id
            row.active_message_id, row.busy_until, row.updated_at = None, None, now()
        return result

    async def fail(self, owner, session_id, message, cancelled):
        async with self.factory.begin() as db:
            row = await db.get(ChatSessionDO, session_id, with_for_update=True)
            current = await db.get(ChatMessageDO, message.id)
            if (
                row
                and current
                and current.attempt == message.attempt
                and current.status == "pending"
            ):
                current.status = "cancelled" if cancelled else "failed"
                current.error = (
                    "处理已中断，可重试最后一条问题"
                    if cancelled
                    else "回答未完成，可重试最后一条问题"
                )
                if row.active_message_id == current.id:
                    row.active_message_id, row.busy_until = None, None

    async def answer(
        self, owner, project, session_id, body, *, events=NOOP_EVENTS, streaming=False
    ):
        message, checkpoint_id, replay = await self.start(
            owner, project, session_id, body
        )
        if replay:
            return replay
        try:
            async with asyncio.timeout(105):
                thread = ChatThread(f"chat:{session_id}", checkpoint_id)
                recovery = []
                if (
                    checkpoint_id
                    and not await self.chat.model_service.checkpoint_exists(thread)
                ):
                    # 如检查点被清理或删除事务回滚，从原始成功记录重建；摘要仍由框架处理。
                    async with self.factory() as db:
                        await self.require(db, owner, project, session_id)
                        rows = await db.scalars(
                            select(ChatMessageDO)
                            .where(
                                ChatMessageDO.session_id == session_id,
                                ChatMessageDO.status == "completed",
                                ChatMessageDO.seq < message.seq,
                            )
                            .order_by(ChatMessageDO.seq)
                        )
                        for old in rows:
                            recovery.extend(
                                [
                                    HumanMessage(content=old.question),
                                    AIMessage(content=old.answer["answer"]),
                                ]
                            )
                    thread.checkpoint_id = None
                result = await self.chat.answer(
                    owner,
                    project,
                    ChatRequestQO(question=body.question),
                    events=events,
                    streaming=streaming,
                    thread=thread,
                    recovery=recovery,
                )
                return await self.finish(
                    owner, project, session_id, message, result, thread.checkpoint_id
                )
        except BaseException as exc:
            try:
                await self.fail(
                    owner, session_id, message, isinstance(exc, asyncio.CancelledError)
                )
            except Exception as cleanup_error:
                # 数据库暂时不可用时保留原始错误；租约到期后仍能恢复执行状态。
                logger.warning(
                    "会话失败状态待恢复；异常类型=%s", type(cleanup_error).__name__
                )
            if isinstance(exc, (TimeoutError, APITimeoutError)):
                raise ApiError(
                    504, "chat_context_timeout", "会话处理超时，请重试"
                ) from exc
            if isinstance(exc, Exception) and not isinstance(exc, ApiError):
                logger.warning("会话处理失败；异常类型=%s", type(exc).__name__)
                raise ApiError(
                    502,
                    "chat_context_unavailable",
                    "会话服务暂时不可用，请稍后重试",
                ) from exc
            raise
