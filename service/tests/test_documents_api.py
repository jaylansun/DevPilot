from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import document_controller as controller
from app.errors import ApiError
from app.models.document_do import DocumentDO, DocumentStatus
from app.services.document_service import MAX_DOCUMENT_BYTES, validate_document


@pytest.mark.parametrize(
    "filename,data,code",
    [
        ("photo.png", b"data", "unsupported_document"),
        ("empty.md", b"  ", "invalid_document_content"),
        ("binary.txt", b"a\x00b", "invalid_document_content"),
        ("gbk.txt", b"\xff\xff", "invalid_document_encoding"),
        ("big.md", b"a" * (MAX_DOCUMENT_BYTES + 1), "document_too_large"),
        ("", b"a", "invalid_filename"),
    ],
    ids=["extension", "empty", "binary", "encoding", "oversized", "filename"],
)
def test_invalid_documents(filename, data, code):
    with pytest.raises(ApiError) as error:
        validate_document(filename, data)
    assert error.value.code == code


def test_normalizes_bom_line_endings_and_never_uses_filename_as_path():
    name, content, digest = validate_document(
        "../../需求.MD", "\ufeff# 需求\r\n正文".encode()
    )
    assert name == "需求.MD"
    assert content == "# 需求\n正文"
    assert digest == validate_document("copy.txt", "# 需求\n正文".encode())[2]


def test_documents_require_member_auth(api_app_factory, reviewer_user):
    path = f"/api/v1/projects/{uuid4()}/documents"
    with TestClient(api_app_factory(None)) as client:
        assert client.get(path).status_code == 401
        assert client.post(path, files={"file": ("x.md", b"test")}).status_code == 401
    with TestClient(api_app_factory(reviewer_user)) as client:
        assert client.get(path).status_code == 403


def test_multipart_upload_returns_accepted_and_hides_raw_content(
    api_app_factory, member_user, monkeypatch
):
    project_id = uuid4()
    timestamp = datetime.now(UTC)
    record = DocumentDO(
        id=uuid4(),
        project_id=project_id,
        filename="需求.md",
        content="私有原文",
        content_hash="a" * 64,
        size_bytes=12,
        status=DocumentStatus.QUEUED,
        chunk_count=0,
        error_message=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    save = AsyncMock(return_value=record)
    monkeypatch.setattr(controller, "require_document_project", AsyncMock())
    monkeypatch.setattr(controller, "upload_document", save)
    with TestClient(api_app_factory(member_user)) as client:
        response = client.post(
            f"/api/v1/projects/{project_id}/documents",
            files={"file": ("需求.md", "正文".encode())},
        )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert "content" not in response.json()
    assert "content_hash" not in response.json()
    assert save.await_args.args[1:3] == (member_user.id, project_id)


def test_body_limit_runs_before_multipart_parser(
    api_app_factory, member_user, monkeypatch
):
    save = AsyncMock()
    monkeypatch.setattr(controller, "upload_document", save)
    with TestClient(api_app_factory(member_user)) as client:
        response = client.post(
            f"/api/v1/projects/{uuid4()}/documents",
            content=b"x" * (3 * 1024 * 1024 + 1),
            headers={"Content-Type": "multipart/form-data; boundary=test"},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    save.assert_not_awaited()
