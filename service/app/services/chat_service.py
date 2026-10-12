import asyncio
import logging
import re
from uuid import UUID

from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain.agents.structured_output import StructuredOutputError
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from openai import APITimeoutError
from pydantic import ValidationError

from app.errors import ApiError
from app.repositories.rag_repository import list_ready_documents
from app.schemas.chat_qo import ChatRequestQO
from app.schemas.chat_vo import (
    ChatAnswerVO,
    ChatCheckArtifactVO,
    ChatCompletion,
    ChatInfoVO,
)
from app.services.chat_business_service import run_requirement_check, run_task_planning
from app.services.chat_context_service import context_answer
from app.services.chat_model_service import ChatThread, invalid_chat
from app.services.document_service import require_document_project
from app.services.planning_read_service import PlanningReadService
from app.services.run_events import NOOP_EVENTS, EventPublisher, trace
from app.services.run_limits import CHAT_TIMEOUT_SECONDS
from app.tools.chat_tools import ChatToolContext

logger = logging.getLogger(__name__)


class ChatService:
    """一次请求独占消息和读取器；模型按需选工具，身份与执行权限由服务端控制。"""

    def __init__(
        self,
        settings,
        index_service,
        session_factory,
        model_service,
        *,
        planner=None,
        workflow=None,
    ):
        self.settings = settings
        self.index_service = index_service
        self.session_factory = session_factory
        self.model_service = model_service
        self.planner = planner
        self.workflow = workflow
        self._slots = asyncio.Semaphore(1)

    @property
    def configured(self) -> bool:
        return self.settings.ai_mode == "mock" or bool(
            self.settings.model_name.strip()
            and self.settings.llm_api_key.get_secret_value().strip()
            and self.settings.llm_base_url.strip()
        )

    async def authorize(self, owner_id, project_id):
        async with self.session_factory() as session:
            await require_document_project(session, owner_id, project_id)

    async def info(self, session, owner_id, project_id) -> ChatInfoVO:
        await require_document_project(session, owner_id, project_id)
        documents = await list_ready_documents(session, project_id)
        return ChatInfoVO(
            mode=self.settings.ai_mode,
            configured=self.configured,
            ready_documents=len(documents),
        )

    async def answer(
        self,
        owner_id: UUID,
        project_id: UUID,
        body: ChatRequestQO,
        *,
        events: EventPublisher = NOOP_EVENTS,
        streaming: bool = False,
        thread: ChatThread | None = None,
        recovery: list | None = None,
    ) -> ChatAnswerVO:
        await self.authorize(owner_id, project_id)
        if not self.configured:
            raise ApiError(
                503, "model_not_configured", "聊天模型尚未配置，请联系部署维护者"
            )
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=1)
        except TimeoutError as exc:
            raise ApiError(
                503, "chat_busy", "当前正在处理其他对话，请稍后再试"
            ) from exc
        try:
            async with asyncio.timeout(CHAT_TIMEOUT_SECONDS):
                # 延迟到真正调用工具才读取项目资料；闲聊不依赖文档或看板规模。
                reader = PlanningReadService(
                    self.session_factory,
                    self.index_service,
                    self.settings.rag_min_score,
                    include_tasks=False,
                )
                board_reader = PlanningReadService(
                    self.session_factory,
                    self.index_service,
                    self.settings.rag_min_score,
                )
                messages = list(recovery or []) + [
                    (HumanMessage if item.role == "user" else AIMessage)(
                        content=item.content
                    )
                    for item in body.history
                ]
                messages.append(HumanMessage(content=body.question))
                context = ChatToolContext(
                    owner_id,
                    project_id,
                    reader,
                    board_reader,
                    events,
                    planner=self.planner,
                    workflow=self.workflow,
                )
                if body.intent == "task_planning":
                    data = await run_task_planning(context, body.question)
                    completion = (
                        data["summary"]
                        + "\n\n已生成任务草案，请展开结果查看任务、假设和风险。"
                    )
                elif body.intent == "requirement_check":
                    data = await run_requirement_check(context, body.question)
                    completion = (
                        data["summary"]
                        + "\n\n请展开检查结果查看覆盖、缺口、待确认事项和本次检查范围。"
                    )
                else:
                    completion = await self.model_service.run(
                        messages, context, thread=thread, streaming=streaming
                    )
                async with trace(events, "validate_result"):
                    result = self._finish(
                        completion, reader, context.board, context.artifacts
                    )
                    if reader.tool_calls:
                        await reader.assert_unchanged(owner_id, project_id)
                        if context.board is not None:
                            await board_reader.assert_unchanged(owner_id, project_id)
                    else:
                        await self.authorize(owner_id, project_id)
                    for artifact_reader in context.artifact_readers:
                        await artifact_reader.assert_unchanged(owner_id, project_id)
                    result._artifact_readers = context.artifact_readers
                if self.settings.ai_mode == "mock":
                    result.mode = "mock"
                    if result.status == "answered":
                        result.status = "demo"
                if body.intent != "auto":
                    if streaming:
                        await events.emit("token", text=result.answer)
                    await self.model_service.record(
                        messages, context_answer(result), thread=thread
                    )
                return result
        except ApiError as exc:
            if exc.code == "planning_context_changed":
                raise ApiError(
                    409,
                    "chat_context_changed",
                    "回答期间项目资料或任务发生变化，请重新提问",
                ) from exc
            if exc.code == "planning_board_too_large":
                raise ApiError(
                    422,
                    "chat_board_too_large",
                    "当前看板超过 100 项，暂时无法完整读取，请缩小项目范围",
                ) from exc
            raise
        except (TimeoutError, APITimeoutError) as exc:
            raise ApiError(
                504, "chat_timeout", "聊天处理超时，请重试或缩小问题范围"
            ) from exc
        except (
            ModelCallLimitExceededError,
            ToolCallLimitExceededError,
            GraphRecursionError,
        ) as exc:
            raise ApiError(
                502, "chat_tool_limit", "本次查询已达到工具调用上限，请缩小问题范围"
            ) from exc
        except (ValidationError, StructuredOutputError) as exc:
            raise invalid_chat() from exc
        except Exception as exc:
            logger.warning("聊天处理失败；异常类型=%s", type(exc).__name__)
            raise ApiError(
                502, "chat_unavailable", "聊天服务暂时不可用，请稍后重试"
            ) from exc
        finally:
            self._slots.release()

    def _finish(
        self, result: ChatCompletion | str, reader, board, artifacts=None
    ) -> ChatAnswerVO:
        artifacts = artifacts or []
        if isinstance(result, str):
            return self._finish_text(result, reader, board, artifacts)
        available = {source.source_id: source for source in reader.sources}
        selected = result.source_ids
        inline = {int(value) for value in re.findall(r"\[(\d+)\]", result.answer)}
        tasks = {UUID(task["id"]): task for task in board["tasks"]} if board else {}
        if (
            len(set(selected)) != len(selected)
            or not set(selected) <= available.keys()
            or (result.basis == "project" and inline != set(selected))
            or len(set(result.task_ids)) != len(result.task_ids)
            or not set(result.task_ids) <= tasks.keys()
        ):
            raise invalid_chat()
        if result.basis == "general":
            if (
                selected
                or result.task_ids
                or reader.tool_calls
                or result.insufficient_evidence
            ):
                raise invalid_chat()
        elif not reader.tool_calls or (
            not result.insufficient_evidence
            and not selected
            and board is None
            and not artifacts
        ):
            raise invalid_chat()
        return ChatAnswerVO(
            answer=result.answer,
            basis=result.basis,
            sources=[available[value] for value in selected],
            tasks=[tasks[value] for value in result.task_ids],
            tool_calls=reader.tool_calls,
            status="insufficient_evidence"
            if result.insufficient_evidence or self._artifact_insufficient(artifacts)
            else "answered",
            mode=self.settings.ai_mode,
            artifacts=artifacts,
        )

    @staticmethod
    def _artifact_insufficient(artifacts):
        return any(
            isinstance(artifact, ChatCheckArtifactVO)
            and artifact.result.status == "insufficient_evidence"
            for artifact in artifacts
        )

    def _finish_text(self, answer: str, reader, board, artifacts=None) -> ChatAnswerVO:
        artifacts = artifacts or []
        if not answer.strip() or len(answer) > 4000:
            raise invalid_chat()
        # 引用只解释为正文中的编号；代码示例、数组下标和 Markdown 链接不是资料引用。
        prose = re.sub(r"```.*?```|~~~.*?~~~|`[^`\n]*`", "", answer, flags=re.DOTALL)
        selected = list(
            dict.fromkeys(
                int(value)
                for value in re.findall(r"(?<![A-Za-z0-9_])\[(\d+)\](?!\()", prose)
            )
        )
        available = {source.source_id: source for source in reader.sources}
        if not set(selected) <= available.keys():
            raise invalid_chat()
        if available and not selected and board is None:
            # 不把遗漏引用的项目回答当作已验证的成功答案。
            raise invalid_chat()
        project_read = bool(reader.tool_calls)
        insufficient = (
            project_read and not available and board is None and not artifacts
        ) or self._artifact_insufficient(artifacts)
        return ChatAnswerVO(
            answer=answer,
            # 表示本轮实际使用的上下文，不作为问题分类或事实正确性的保证。
            basis="project" if project_read else "general",
            sources=[available[value] for value in selected],
            # 展示真实查询记录，不能从自然语言猜测模型选择了哪些任务。
            tasks=board["tasks"] if board is not None else [],
            tool_calls=reader.tool_calls,
            status="insufficient_evidence" if insufficient else "answered",
            mode=self.settings.ai_mode,
            artifacts=artifacts,
        )
