from uuid import UUID

from fastapi import APIRouter, UploadFile

from app.api.dependencies import DatabaseSession, MemberUser
from app.schemas.document_vo import DocumentListVO, DocumentVO
from app.services.document_service import (
    MAX_DOCUMENT_BYTES,
    change_document_state,
    get_documents,
    require_document_project,
    upload_document,
)

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["知识库"])


@router.get("", response_model=DocumentListVO, summary="查看项目文档及索引状态")
async def list_documents(
    project_id: UUID, session: DatabaseSession, current_user: MemberUser
):
    documents = await get_documents(session, current_user.id, project_id)
    return DocumentListVO(
        items=[DocumentVO.model_validate(doc) for doc in documents],
        total=len(documents),
    )


@router.post(
    "", response_model=DocumentVO, status_code=202, summary="上传文档并加入后台索引队列"
)
async def create_document(
    project_id: UUID,
    file: UploadFile,
    session: DatabaseSession,
    current_user: MemberUser,
):
    try:
        await require_document_project(session, current_user.id, project_id)
        data = await file.read(MAX_DOCUMENT_BYTES + 1)
        document = await upload_document(
            session, current_user.id, project_id, file.filename, data
        )
        return DocumentVO.model_validate(document)
    finally:
        await file.close()


@router.post(
    "/{document_id}/retry",
    response_model=DocumentVO,
    status_code=202,
    summary="重试失败的文档处理",
)
async def retry_document(
    project_id: UUID,
    document_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
):
    document = await change_document_state(
        session, current_user.id, project_id, document_id, delete=False
    )
    return DocumentVO.model_validate(document)


@router.delete(
    "/{document_id}",
    response_model=DocumentVO,
    status_code=202,
    summary="删除文档及其向量",
)
async def delete_document(
    project_id: UUID,
    document_id: UUID,
    session: DatabaseSession,
    current_user: MemberUser,
):
    # 返回 202 代表已受理；后台先删除向量，再删除文档记录，不能提前声称删除完成。
    document = await change_document_state(
        session, current_user.id, project_id, document_id, delete=True
    )
    return DocumentVO.model_validate(document)
