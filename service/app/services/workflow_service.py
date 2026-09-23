import asyncio
import logging
from uuid import UUID

from langgraph.errors import GraphRecursionError
from openai import APITimeoutError
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models.task_do import TaskDO
from app.repositories.rag_repository import list_ready_documents
from app.schemas.workflow_qo import WorkflowRequestQO
from app.schemas.workflow_vo import WorkflowInfoVO, WorkflowResultVO
from app.services.document_service import require_document_project
from app.services.planning_read_service import PlanningReadService
from app.services.run_events import NOOP_EVENTS, EventPublisher
from app.services.workflow_graph import WorkflowContext, WorkflowGraph

logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(
        self, settings, index_service, session_factory, model_service, rag_model_service
    ):
        self.settings = settings
        self.index_service = index_service
        self.session_factory = session_factory
        self.workflow = WorkflowGraph(settings, model_service, rag_model_service)
        self._slots = asyncio.Semaphore(1)

    @property
    def configured(self) -> bool:
        return self.settings.ai_mode == "mock" or bool(
            self.settings.model_name.strip()
            and self.settings.llm_api_key.get_secret_value().strip()
            and self.settings.llm_base_url.strip()
        )

    async def info(
        self, session: AsyncSession, owner_id: UUID, project_id: UUID
    ) -> WorkflowInfoVO:
        await require_document_project(session, owner_id, project_id)
        documents = await list_ready_documents(session, project_id)
        count = await session.scalar(
            select(func.count(TaskDO.id)).where(TaskDO.project_id == project_id)
        )
        return WorkflowInfoVO(
            mode=self.settings.ai_mode,
            configured=self.configured,
            ready_documents=len(documents),
            task_count=count or 0,
        )

    async def run(
        self,
        owner_id: UUID,
        project_id: UUID,
        body: WorkflowRequestQO,
        *,
        events: EventPublisher = NOOP_EVENTS,
        streaming: bool = False,
    ) -> WorkflowResultVO:
        async with self.session_factory() as session:
            await require_document_project(session, owner_id, project_id)
        if not self.configured:
            raise ApiError(
                503,
                "model_not_configured",
                "真实模式尚未配置模型，请联系部署维护者完成配置",
            )
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=1)
        except TimeoutError as exc:
            raise ApiError(
                503, "workflow_busy", "当前正在处理其他检查，请稍后重试"
            ) from exc
        try:
            async with asyncio.timeout(65):
                documents = PlanningReadService(
                    self.session_factory,
                    self.index_service,
                    self.settings.rag_min_score,
                )
                # 身份与读取器在服务端构造，模型和请求体都不能设置；不共享 AsyncSession。
                await documents.assert_unchanged(owner_id, project_id)
                context = WorkflowContext(
                    owner_id,
                    project_id,
                    documents,
                    documents.fork(),
                    events=events,
                    streaming=streaming,
                )
                state = await self.workflow.graph.ainvoke(
                    {"message": body.message, "requested_intent": body.intent},
                    context=context,
                    config={"recursion_limit": 12},
                )
                return state["result"]
        except ApiError as exc:
            if exc.code == "planning_context_changed":
                raise ApiError(
                    409,
                    "workflow_context_changed",
                    "检查期间项目、任务或就绪文档发生变化，请重新检查",
                ) from exc
            if exc.code == "planning_board_too_large":
                raise ApiError(
                    422,
                    "workflow_board_too_large",
                    "当前看板超过 100 项，无法完整对照，请缩小项目范围",
                ) from exc
            raise
        except (TimeoutError, APITimeoutError) as exc:
            raise ApiError(
                504, "workflow_timeout", "处理超时，请缩小范围后重试"
            ) from exc
        except (ValidationError, GraphRecursionError) as exc:
            raise ApiError(
                502, "invalid_workflow_result", "模型返回的检查结果不符合格式，请重试"
            ) from exc
        except Exception as exc:
            logger.warning("项目只读流程失败；异常类型=%s", type(exc).__name__)
            raise ApiError(
                502,
                "workflow_unavailable",
                "检查暂时不可用，请检查模型、网络和文档索引后重试",
            ) from exc
        finally:
            self._slots.release()
