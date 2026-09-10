from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import project_controller as projects_api
from app.models.project_do import ProjectDO
from app.models.user_do import UserDO
from app.services.project_service import ProjectNameAlreadyExistsError, ProjectNotFoundError


def make_project(owner_id: UUID) -> ProjectDO:
    timestamp = datetime.now(UTC)
    return ProjectDO(
        id=uuid4(),
        owner_id=owner_id,
        name="DevPilot",
        description="AI 项目协作助手",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_project_api_requires_login(
    api_app_factory,
) -> None:
    with TestClient(api_app_factory(None)) as client:
        response = client.get("/api/v1/projects")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_reviewer_cannot_create_member_project(
    api_app_factory,
    reviewer_user: UserDO,
) -> None:
    with TestClient(api_app_factory(reviewer_user)) as client:
        response = client.post("/api/v1/projects", json={"name": "审批项目"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_permissions"


def test_project_list_returns_page(
    api_app_factory,
    member_user: UserDO,
    monkeypatch,
) -> None:
    project = make_project(member_user.id)
    query = AsyncMock(return_value=([project], 1))
    monkeypatch.setattr(projects_api, "get_projects_page", query)

    with TestClient(api_app_factory(member_user)) as client:
        response = client.get("/api/v1/projects?offset=0&limit=10")

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "DevPilot"
    assert response.json()["total"] == 1
    query.assert_awaited_once_with(
        ANY,
        member_user.id,
        offset=0,
        limit=10,
    )


def test_project_not_owned_by_user_is_hidden_as_not_found(
    api_app_factory,
    member_user: UserDO,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        projects_api,
        "get_project_record",
        AsyncMock(side_effect=ProjectNotFoundError("项目不存在")),
    )

    with TestClient(api_app_factory(member_user)) as client:
        response = client.get(f"/api/v1/projects/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_not_found"


def test_duplicate_project_name_returns_conflict(
    api_app_factory,
    member_user: UserDO,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        projects_api,
        "create_project_record",
        AsyncMock(side_effect=ProjectNameAlreadyExistsError("项目名称已存在")),
    )

    with TestClient(api_app_factory(member_user)) as client:
        response = client.post("/api/v1/projects", json={"name": "DevPilot"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "project_name_exists"


def test_project_validation_rejects_blank_name_and_extra_fields(
    api_app_factory,
    member_user: UserDO,
) -> None:
    with TestClient(api_app_factory(member_user)) as client:
        response = client.post(
            "/api/v1/projects",
            json={"name": "   ", "owner_id": str(uuid4())},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
