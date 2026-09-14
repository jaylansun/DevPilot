import hashlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.repositories.document_repository import (
    get_project_document,
    list_project_documents,
)
from app.repositories.project_repository import get_owned_project

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_PROJECT_DOCUMENTS = 20


def validate_document(filename: str | None, data: bytes) -> tuple[str, str, str]:
    """只接受 UTF-8 文本，文件名仅做展示，绝不作为磁盘路径。"""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise ApiError(
            status_code=422,
            code="invalid_filename",
            message="文件名不能为空、包含控制字符或超过 255 个字符",
        )
    if not name.lower().endswith((".md", ".txt")):
        raise ApiError(
            status_code=415,
            code="unsupported_document",
            message="仅支持 .md 和 .txt 文件",
        )
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ApiError(
            status_code=413, code="document_too_large", message="文件不能超过 2 MB"
        )
    try:
        content = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise ApiError(
            status_code=422,
            code="invalid_document_encoding",
            message="请将文件另存为 UTF-8 编码后上传",
        ) from exc
    if not content.strip() or "\x00" in content:
        raise ApiError(
            status_code=422,
            code="invalid_document_content",
            message="文件不能为空或包含二进制内容",
        )
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return name, content, digest


async def require_document_project(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    *,
    lock: bool = False,
) -> None:
    if await get_owned_project(session, project_id, owner_id, lock=lock) is None:
        raise ApiError(status_code=404, code="project_not_found", message="项目不存在")


async def get_documents(
    session: AsyncSession, owner_id: UUID, project_id: UUID
) -> list[DocumentDO]:
    await require_document_project(session, owner_id, project_id)
    return await list_project_documents(session, project_id)


async def upload_document(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    filename: str | None,
    data: bytes,
) -> DocumentDO:
    # 按项目串行处理上传，防止并发突破数量限制或重复提交相同内容。
    await require_document_project(session, owner_id, project_id, lock=True)
    name, content, digest = validate_document(filename, data)
    documents = await list_project_documents(session, project_id)
    if any(document.content_hash == digest for document in documents):
        raise ApiError(
            status_code=409,
            code="document_exists",
            message="当前项目已上传相同内容，请查看原文档的状态",
        )
    if len(documents) >= MAX_PROJECT_DOCUMENTS:
        raise ApiError(
            status_code=409,
            code="document_limit_reached",
            message="每个项目最多上传 20 个文档，请先删除不需要的文档",
        )
    document = DocumentDO(
        project_id=project_id,
        filename=name,
        content=content,
        content_hash=digest,
        size_bytes=len(data),
    )
    session.add(document)
    await session.flush()
    await session.refresh(document)
    return document


async def change_document_state(
    session: AsyncSession,
    owner_id: UUID,
    project_id: UUID,
    document_id: UUID,
    *,
    delete: bool,
) -> DocumentDO:
    await require_document_project(session, owner_id, project_id, lock=True)
    document = await get_project_document(session, project_id, document_id)
    if document is None:
        raise ApiError(status_code=404, code="document_not_found", message="文档不存在")
    if delete or document.status == DocumentStatus.DELETE_FAILED:
        document.status = DocumentStatus.DELETING
    elif document.status == DocumentStatus.FAILED:
        document.status = DocumentStatus.QUEUED
    else:
        raise ApiError(
            status_code=409,
            code="document_not_retryable",
            message="只有处理失败的文档可以重试",
        )
    document.error_message = None
    await session.flush()
    await session.refresh(document)
    return document
