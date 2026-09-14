import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.models.document_do import DocumentDO, DocumentStatus
from app.models.vector_cleanup_do import VectorCleanupDO

logger = logging.getLogger(__name__)


class DocumentWorkerService:
    """数据库作为持久任务队列；仅支持当前计划中的一个 API 实例、一个工作进程。"""

    def __init__(self, session_factory, index_service):
        self.session_factory = session_factory
        self.index_service = index_service

    async def recover(self):
        # 上次进程中断的索引可安全重建；向量 ID 固定，重试不会产生重复片段。
        async with self.session_factory.begin() as session:
            await session.execute(
                update(DocumentDO)
                .where(
                    DocumentDO.status == DocumentStatus.INDEXING,
                )
                .values(status=DocumentStatus.QUEUED, chunk_count=0)
            )

    async def process_once(self) -> bool:
        async with self.session_factory.begin() as session:
            cleanup = await session.scalar(
                select(VectorCleanupDO)
                .where(
                    VectorCleanupDO.next_attempt_at <= datetime.now(UTC),
                )
                .order_by(VectorCleanupDO.next_attempt_at)
                .limit(1)
            )
            cleanup_id = cleanup.project_id if cleanup else None
        if cleanup_id is not None:
            try:
                await asyncio.to_thread(self.index_service.delete_project, cleanup_id)
                async with self.session_factory.begin() as session:
                    job = await session.get(VectorCleanupDO, cleanup_id)
                    if job:
                        await session.delete(job)
            except Exception:
                logger.exception("项目向量清理失败；项目 ID=%s", cleanup_id)
                async with self.session_factory.begin() as session:
                    job = await session.get(VectorCleanupDO, cleanup_id)
                    if job:
                        job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=60)
            return True

        async with self.session_factory.begin() as session:
            # 优先处理删除，避免删除任务排在普通上传之后。
            document = await session.scalar(
                select(DocumentDO)
                .where(
                    DocumentDO.status.in_(
                        [DocumentStatus.QUEUED, DocumentStatus.DELETING]
                    ),
                )
                .order_by(
                    DocumentDO.status != DocumentStatus.DELETING, DocumentDO.created_at
                )
                .limit(1)
                .with_for_update()
            )
            if document is None:
                return False
            document_id, project_id = document.id, document.project_id
            deleting = document.status == DocumentStatus.DELETING
            filename, content = document.filename, document.content
            if not deleting:
                document.status = DocumentStatus.INDEXING
                document.chunk_count = 0
                document.error_message = None

        try:
            if deleting:
                await asyncio.to_thread(
                    self.index_service.delete_document, project_id, document_id
                )
                async with self.session_factory.begin() as session:
                    document = await session.get(
                        DocumentDO, document_id, with_for_update=True
                    )
                    if document:
                        await session.delete(document)
            else:
                count = await asyncio.to_thread(
                    self.index_service.index,
                    project_id,
                    document_id,
                    filename,
                    content,
                )
                async with self.session_factory.begin() as session:
                    document = await session.get(
                        DocumentDO, document_id, with_for_update=True
                    )
                    # 索引期间可能收到删除请求，不允许重新把文档改成可用。
                    if document and document.status == DocumentStatus.INDEXING:
                        document.status = DocumentStatus.READY
                        document.chunk_count = count
            return True
        except Exception:
            logger.exception("文档处理失败；文档 ID=%s；删除=%s", document_id, deleting)
            async with self.session_factory.begin() as session:
                document = await session.get(
                    DocumentDO, document_id, with_for_update=True
                )
                expected = (
                    DocumentStatus.DELETING if deleting else DocumentStatus.INDEXING
                )
                if document and document.status == expected:
                    document.status = (
                        DocumentStatus.DELETE_FAILED
                        if deleting
                        else DocumentStatus.FAILED
                    )
                    document.error_message = (
                        "向量清理失败，请重试删除；持续失败请查看服务日志"
                        if deleting
                        else "索引失败，请检查服务的模型下载网络、磁盘空间和日志后重试"
                    )
            return True

    async def run(self):
        # 数据库暂时不可用时也保留重启恢复逻辑，避免一直遗留 indexing 状态。
        recovered = False
        while True:
            try:
                if not recovered:
                    await self.recover()
                    recovered = True
                if await self.process_once():
                    await asyncio.sleep(0)
                    continue
            except Exception:
                logger.exception("知识库后台任务暂时不可用，稍后重试")
            await asyncio.sleep(3)
