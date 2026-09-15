import asyncio
import logging
from uuid import UUID

from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langgraph.errors import GraphRecursionError
from openai import APITimeoutError
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.models.task_do import TaskDO
from app.repositories.rag_repository import list_ready_documents
from app.schemas.plan_vo import (
    PlanInfoVO,
    PlanProposalVO,
    PlanResultVO,
    normalize_task_title,
)
from app.services.document_service import require_document_project
from app.services.planning_read_service import PlanningReadService
from app.tools.planning_tools import PlanToolContext

logger = logging.getLogger(__name__)


def validate_proposal_sources(proposal: PlanProposalVO, reader: PlanningReadService) -> None:
    """只验证可机械检查的约束，不把校验通过说成需求分析一定正确。"""
    executed = {call["name"] for call in reader.tool_calls}
    if not {"search_documents", "read_task_board"} <= executed:
        raise ApiError(502, "planning_missing_tools", "模型尚未完成文档和看板读取，请重试")
    if not reader.sources:
        raise ApiError(409, "planning_no_evidence", "没有找到相关文档片段，请补充资料或调整规划目标")
    available = {source.source_id for source in reader.sources}
    selected = {source_id for task in proposal.tasks for source_id in task.source_ids}
    if not selected or not selected <= available:
        raise ApiError(502, "invalid_plan_sources", "任务方案没有提供有效的文档依据，请重试")
    existing = {normalize_task_title(title) for title in reader.existing_titles}
    if any(normalize_task_title(task.title) in existing for task in proposal.tasks):
        raise ApiError(502, "duplicate_plan_task", "方案中存在与当前看板重复的任务标题，请调整目标后重试")


class PlanService:
    """仅生成临时草案；不创建任务、审批记录、会话或持久检查点。"""

    def __init__(self, settings: Settings, index_service, session_factory, agent_service):
        self.settings = settings
        self.index_service = index_service
        self.session_factory = session_factory
        self.agent_service = agent_service
        self._slots = asyncio.Semaphore(1)

    @property
    def configured(self) -> bool:
        return self.settings.ai_mode == "mock" or bool(
            self.settings.model_name.strip()
            and self.settings.llm_api_key.get_secret_value().strip()
            and self.settings.llm_base_url.strip()
        )

    async def info(self, session: AsyncSession, owner_id: UUID, project_id: UUID) -> PlanInfoVO:
        await require_document_project(session, owner_id, project_id)
        documents = await list_ready_documents(session, project_id)
        count = await session.scalar(
            select(func.count(TaskDO.id)).where(TaskDO.project_id == project_id)
        )
        return PlanInfoVO(
            mode=self.settings.ai_mode,
            configured=self.configured,
            ready_documents=len(documents),
            task_count=count or 0,
        )

    async def create(
        self, session: AsyncSession, owner_id: UUID, project_id: UUID, goal: str
    ) -> PlanResultVO:
        await require_document_project(session, owner_id, project_id)
        if not await list_ready_documents(session, project_id):
            raise ApiError(409, "planning_no_documents", "请先上传项目文档并等待索引完成，再生成任务草案")
        if not self.configured:
            raise ApiError(503, "model_not_configured", "真实规划尚未配置模型，请设置 MODEL_NAME、LLM_API_KEY 和 LLM_BASE_URL")
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=1)
        except TimeoutError as exc:
            raise ApiError(503, "planning_busy", "当前正在生成其他方案，请稍后再试") from exc
        try:
            async with asyncio.timeout(65):
                # 工具上下文只在本次请求内存在，身份不交给模型填写。
                reader = PlanningReadService(
                    self.session_factory, self.index_service, self.settings.rag_min_score
                )
                context = PlanToolContext(owner_id, project_id, reader)
                proposal = await self.agent_service.generate(goal, context)
                proposal = PlanProposalVO.model_validate(proposal.model_dump())
                validate_proposal_sources(proposal, reader)
                await reader.assert_unchanged(owner_id, project_id)
                return PlanResultVO(
                    mode=self.settings.ai_mode,
                    proposal=proposal,
                    sources=reader.sources,
                    tool_calls=reader.tool_calls,
                    board_task_count=reader.board_task_count,
                )
        except ApiError:
            raise
        except (TimeoutError, APITimeoutError) as exc:
            raise ApiError(504, "planning_timeout", "任务规划超时，请缩小目标范围后重试") from exc
        except (ModelCallLimitExceededError, ToolCallLimitExceededError, GraphRecursionError) as exc:
            raise ApiError(502, "planning_limit", "规划已达到调用次数上限，请缩小目标范围后重试") from exc
        except ValidationError as exc:
            raise ApiError(502, "invalid_plan", "模型返回的任务方案不符合格式或依赖规则，请重试") from exc
        except Exception as exc:
            logger.warning("任务规划失败；异常类型=%s", type(exc).__name__)
            raise ApiError(502, "planning_unavailable", "任务规划暂时不可用，请检查模型、网络与文档索引后重试") from exc
        finally:
            self._slots.release()
