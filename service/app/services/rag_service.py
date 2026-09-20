import asyncio
import logging
import re
from uuid import UUID

from openai import APITimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.repositories.rag_repository import list_ready_documents
from app.schemas.rag_vo import GroundedAnswerVO, RagAnswerVO, RagInfoVO, RagSourceVO
from app.services.document_service import require_document_project
from app.services.run_stream_service import trace

logger = logging.getLogger(__name__)
UNKNOWN_ANSWER = (
    "当前项目文档中没有足够依据回答这个问题。请补充相关资料，或换一个更具体的问题。"
)


def build_answer(
    result: GroundedAnswerVO, sources: list[RagSourceVO], mode: str
) -> RagAnswerVO:
    """引用只能来自服务端检索结果，模型不决定路径、文档身份或片段内容。"""
    if result.insufficient_evidence:
        return RagAnswerVO(
            answer=UNKNOWN_ANSWER, sources=[], status="insufficient_evidence", mode=mode
        )
    available = {source.source_id: source for source in sources}
    selected = list(dict.fromkeys(result.source_ids))
    inline = {int(value) for value in re.findall(r"\[(\d+)\]", result.answer)}
    if not selected or not set(selected) <= available.keys() or inline != set(selected):
        raise ApiError(
            502, "invalid_model_citations", "模型没有返回有效的资料引用，请重试"
        )
    return RagAnswerVO(
        answer=result.answer,
        sources=[available[value] for value in selected],
        status="answered",
        mode=mode,
    )


class RagService:
    """两步问答：先限定范围检索，再带来源生成；不引入 Agent 或写操作。"""

    def __init__(self, settings: Settings, index_service, model_service):
        self.settings = settings
        self.index_service = index_service
        self.model_service = model_service
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
    ) -> RagInfoVO:
        await require_document_project(session, owner_id, project_id)
        documents = await list_ready_documents(session, project_id)
        return RagInfoVO(
            mode=self.settings.ai_mode,
            configured=self.configured,
            ready_documents=len(documents),
        )

    async def answer(
        self, session: AsyncSession, owner_id: UUID, project_id: UUID, question: str
    ) -> RagAnswerVO:
        # 越权请求必须在任何检索或模型调用之前被拒绝。
        await require_document_project(session, owner_id, project_id)
        documents = await list_ready_documents(session, project_id)
        if not documents:
            return RagAnswerVO(
                answer="项目中还没有已就绪的文档，请先到知识库上传资料并等待索引完成。",
                sources=[],
                status="insufficient_evidence",
                mode=self.settings.ai_mode,
            )
        if not self.configured:
            raise ApiError(
                503,
                "model_not_configured",
                "真实问答尚未配置模型，请设置 MODEL_NAME、LLM_API_KEY 和 LLM_BASE_URL",
            )
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=1)
        except TimeoutError as exc:
            raise ApiError(503, "rag_busy", "当前正在处理其他问题，请稍后再试") from exc
        try:
            async with asyncio.timeout(65):
                async with trace("retrieve_knowledge"):
                    chunks = await asyncio.to_thread(
                        self.index_service.search,
                        project_id,
                        list(documents),
                        question,
                        limit=4,
                        min_score=self.settings.rag_min_score,
                    )
                    # 等待索引锁期间，文档可能被删除或改成不可用；发送给模型前再次检查。
                    await require_document_project(session, owner_id, project_id)
                    current = await list_ready_documents(session, project_id)
                    sources = [
                        RagSourceVO(
                            source_id=i + 1,
                            document_id=chunk.document_id,
                            filename=current[chunk.document_id],
                            chunk_index=chunk.chunk_index,
                            heading=chunk.heading,
                            text=chunk.text,
                        )
                        for i, chunk in enumerate(chunks)
                        if chunk.document_id in current
                    ]
                if not sources:
                    return RagAnswerVO(
                        answer=UNKNOWN_ANSWER,
                        sources=[],
                        status="insufficient_evidence",
                        mode=self.settings.ai_mode,
                    )
                async with trace("answer_knowledge"):
                    result = await self.model_service.answer(question, sources)
                async with trace("validate_result"):
                    answer = build_answer(result, sources, self.settings.ai_mode)
                    # 模型调用期间已删除的资料不能再作为当前有效引用返回。
                    await require_document_project(session, owner_id, project_id)
                    latest = await list_ready_documents(session, project_id)
                    if any(source.document_id not in latest for source in sources):
                        raise ApiError(
                            409,
                            "knowledge_changed",
                            "回答期间知识库发生变化，请重新提问",
                        )
                return answer
        except ApiError:
            raise
        except (TimeoutError, APITimeoutError) as exc:
            raise ApiError(504, "rag_timeout", "问答处理超时，请稍后重试") from exc
        except Exception as exc:
            # 不记录第三方异常正文，避免把密钥、问题或原文写入日志。
            logger.warning("知识库问答失败；异常类型=%s", type(exc).__name__)
            raise ApiError(
                502,
                "rag_unavailable",
                "知识库问答暂时不可用，请检查模型配置、网络和索引后重试",
            ) from exc
        finally:
            self._slots.release()
