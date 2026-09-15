import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO
from app.repositories.rag_repository import list_ready_documents
from app.schemas.rag_vo import RagSourceVO
from app.services.document_service import require_document_project

MAX_BOARD_TASKS = 100
MAX_SOURCES = 12
MAX_EXCERPT_LENGTH = 400


@dataclass(frozen=True)
class _PlanningRead:
    ready_documents: dict[UUID, str]
    tasks: list[TaskDO]
    snapshot: tuple


class PlanningReadService:
    """一次规划独占的只读资料读取器；不把会话交给并发工具共享。"""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        index_service,
        min_score: float = 0.5,
    ) -> None:
        self.session_factory = session_factory
        self.index_service = index_service
        self.min_score = min_score
        self.sources: list[RagSourceVO] = []
        self.tool_calls: list[dict] = []
        self.board_task_count = 0
        self.existing_titles: list[str] = []
        self._lock = asyncio.Lock()
        self._snapshot: tuple | None = None
        self._scope: tuple[UUID, UUID] | None = None
        self._source_ids: dict[tuple[UUID, int], int] = {}

    @staticmethod
    def _changed() -> ApiError:
        return ApiError(
            409,
            "planning_context_changed",
            "规划期间项目、任务或就绪文档发生变化，请重新生成规划",
        )

    async def _read_context(self, owner_id: UUID, project_id: UUID) -> _PlanningRead:
        # 每次复核都创建并关闭自己的会话，避免事务快照或对象缓存掩盖变化。
        async with self.session_factory() as session:
            await require_document_project(session, owner_id, project_id)
            project = (
                await session.execute(
                    select(
                        ProjectDO.id,
                        ProjectDO.updated_at,
                        ProjectDO.name,
                        ProjectDO.description,
                    ).where(ProjectDO.id == project_id)
                )
            ).one_or_none()
            if project is None:
                raise self._changed()
            tasks = list(
                await session.scalars(
                    select(TaskDO)
                    .where(TaskDO.project_id == project_id)
                    .order_by(TaskDO.id)
                    .limit(MAX_BOARD_TASKS + 1)
                )
            )
            if len(tasks) > MAX_BOARD_TASKS:
                if self._snapshot is not None:
                    raise self._changed()
                raise ApiError(
                    422,
                    "planning_board_too_large",
                    "当前看板超过 100 个任务，无法完整读取并检查重复任务，请缩小项目范围",
                )
            documents = await list_ready_documents(session, project_id)
            versions = list(
                await session.execute(
                    select(
                        DocumentDO.id,
                        DocumentDO.updated_at,
                        DocumentDO.content_hash,
                        DocumentDO.filename,
                        DocumentDO.chunk_count,
                        DocumentDO.size_bytes,
                    )
                    .where(
                        DocumentDO.project_id == project_id,
                        DocumentDO.status == DocumentStatus.READY,
                    )
                    .order_by(DocumentDO.id)
                )
            )
            # 两次 SQL 之间刚好更新状态时也不能将不一致资料作为基线。
            if documents != {row.id: row.filename for row in versions}:
                raise self._changed()
            snapshot = (
                tuple(project),
                tuple(
                    (
                        task.id,
                        task.version,
                        task.updated_at,
                        task.title,
                        task.description,
                        task.status,
                        task.priority,
                        task.acceptance_criteria,
                    )
                    for task in tasks
                ),
                tuple(tuple(row) for row in versions),
            )
            return _PlanningRead(documents, tasks, snapshot)

    def _check_snapshot(
        self, current: _PlanningRead, owner_id: UUID, project_id: UUID
    ) -> None:
        scope = (owner_id, project_id)
        if self._snapshot is None:
            self._snapshot = current.snapshot
            self._scope = scope
        elif self._scope != scope or self._snapshot != current.snapshot:
            raise self._changed()

    def _record_call(self, name: str, count: int) -> str:
        status = "success" if count else "empty"
        self.tool_calls.append({"name": name, "status": status, "item_count": count})
        return status

    async def search_documents(
        self, owner_id: UUID, project_id: UUID, query: str
    ) -> dict:
        if (
            not isinstance(query, str)
            or not 1 <= len(query) <= 2000
            or not query.strip()
        ):
            raise ApiError(
                422, "invalid_planning_query", "检索内容须为 1 至 2000 个字符"
            )
        async with self._lock:
            current = await self._read_context(owner_id, project_id)
            self._check_snapshot(current, owner_id, project_id)
            chunks = []
            if current.ready_documents:
                chunks = await asyncio.to_thread(
                    self.index_service.search,
                    project_id,
                    list(current.ready_documents),
                    query.strip(),
                    limit=4,
                    min_score=self.min_score,
                )
            latest = await self._read_context(owner_id, project_id)
            self._check_snapshot(latest, owner_id, project_id)
            selected: list[RagSourceVO] = []
            selected_keys: set[tuple[UUID, int]] = set()
            truncated = False
            for chunk in chunks[:4]:
                if chunk.document_id not in latest.ready_documents:
                    continue
                truncated = truncated or (
                    len(chunk.text) > MAX_EXCERPT_LENGTH
                    or len(chunk.heading) > MAX_EXCERPT_LENGTH
                )
                key = (chunk.document_id, chunk.chunk_index)
                if key in selected_keys:
                    continue
                selected_keys.add(key)
                source_id = self._source_ids.get(key)
                if source_id is None:
                    if len(self.sources) >= MAX_SOURCES:
                        truncated = True
                        continue
                    source_id = len(self.sources) + 1
                    source = RagSourceVO(
                        source_id=source_id,
                        document_id=chunk.document_id,
                        filename=latest.ready_documents[chunk.document_id],
                        chunk_index=chunk.chunk_index,
                        heading=chunk.heading[:MAX_EXCERPT_LENGTH],
                        text=chunk.text[:MAX_EXCERPT_LENGTH],
                    )
                    self._source_ids[key] = source_id
                    self.sources.append(source)
                selected.append(self.sources[source_id - 1])
            status = self._record_call("search_documents", len(selected))
            return {
                "status": status,
                "sources": [source.model_dump(mode="json") for source in selected],
                "truncated": truncated,
                "truncation_note": (
                    "本次规划最多保留 12 段资料，每段最多 400 个字符。"
                    if truncated
                    else "资料片段每段最多保留 400 个字符。"
                ),
            }

    async def read_task_board(self, owner_id: UUID, project_id: UUID) -> dict:
        async with self._lock:
            current = await self._read_context(owner_id, project_id)
            self._check_snapshot(current, owner_id, project_id)
            latest = await self._read_context(owner_id, project_id)
            self._check_snapshot(latest, owner_id, project_id)
            self.board_task_count = len(latest.tasks)
            self.existing_titles = [task.title for task in latest.tasks]
            tasks = [
                {
                    "id": str(task.id),
                    "title": task.title,
                    "status": task.status.value,
                    "priority": task.priority,
                    "description": task.description[:MAX_EXCERPT_LENGTH],
                    "acceptance_criteria": task.acceptance_criteria[
                        :MAX_EXCERPT_LENGTH
                    ],
                    "description_truncated": len(task.description) > MAX_EXCERPT_LENGTH,
                    "acceptance_criteria_truncated": (
                        len(task.acceptance_criteria) > MAX_EXCERPT_LENGTH
                    ),
                }
                for task in latest.tasks
            ]
            truncated = any(
                task["description_truncated"] or task["acceptance_criteria_truncated"]
                for task in tasks
            )
            return {
                "status": self._record_call("read_task_board", len(tasks)),
                "tasks": tasks,
                "total": self.board_task_count,
                "truncated": truncated,
                "truncation_note": (
                    "已读取全部任务；过长的说明与验收标准各保留前 400 个字符，标题完整保留。"
                    if truncated
                    else "已读取全部任务，未截断任务内容。"
                ),
            }

    async def assert_unchanged(self, owner_id: UUID, project_id: UUID) -> None:
        async with self._lock:
            current = await self._read_context(owner_id, project_id)
            self._check_snapshot(current, owner_id, project_id)
