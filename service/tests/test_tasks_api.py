from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.v1 import task_controller as tasks_api
from app.models.task_do import TaskDO, TaskSource, TaskStatus
from app.models.user_do import UserDO
from app.services.task_service import TaskNotFoundError, TaskVersionConflictError


def make_task(project_id: UUID) -> TaskDO:
    timestamp = datetime.now(UTC)
    return TaskDO(
        id=uuid4(),
        project_id=project_id,
        title="完成任务接口",
        description="",
        priority=2,
        status=TaskStatus.TODO,
        acceptance_criteria="接口测试通过",
        source=TaskSource.MANUAL,
        version=1,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_task_list_supports_pagination_and_filters(
    api_app_factory,
    member_user: UserDO,
    monkeypatch,
) -> None:
    project_id = uuid4()
    task = make_task(project_id)
    query = AsyncMock(return_value=([task], 1))
    monkeypatch.setattr(tasks_api, "get_tasks_page", query)

    with TestClient(api_app_factory(member_user)) as client:
        response = client.get(
            f"/api/v1/projects/{project_id}/tasks"
            "?offset=0&limit=10&status=todo&priority=2"
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["source"] == "manual"
    assert response.json()["total"] == 1
    query.assert_awaited_once_with(
        ANY,
        member_user.id,
        project_id,
        offset=0,
        limit=10,
        task_status=TaskStatus.TODO,
        priority=2,
    )


def test_task_patch_only_sends_present_fields(
    api_app_factory,
    member_user: UserDO,
    monkeypatch,
) -> None:
    project_id = uuid4()
    task = make_task(project_id)
    task.status = TaskStatus.DONE
    task.version = 2
    update = AsyncMock(return_value=task)
    monkeypatch.setattr(tasks_api, "update_task_record", update)

    with TestClient(api_app_factory(member_user)) as client:
        response = client.patch(
            f"/api/v1/projects/{project_id}/tasks/{task.id}",
            json={"version": 1, "status": "done"},
        )

    assert response.status_code == 200
    assert response.json()["version"] == 2
    update.assert_awaited_once_with(
        ANY,
        member_user.id,
        project_id,
        task.id,
        expected_version=1,
        changes={"status": TaskStatus.DONE},
    )


def test_stale_task_version_returns_conflict(
    api_app_factory,
    member_user: UserDO,
    monkeypatch,
) -> None:
    project_id = uuid4()
    task_id = uuid4()
    monkeypatch.setattr(
        tasks_api,
        "update_task_record",
        AsyncMock(side_effect=TaskVersionConflictError("任务版本已经发生变化")),
    )

    with TestClient(api_app_factory(member_user)) as client:
        response = client.patch(
            f"/api/v1/projects/{project_id}/tasks/{task_id}",
            json={"version": 1, "priority": 1},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "task_version_conflict"


def test_other_users_task_is_hidden_as_not_found(
    api_app_factory,
    member_user: UserDO,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        tasks_api,
        "get_task_record",
        AsyncMock(side_effect=TaskNotFoundError("任务不存在")),
    )

    with TestClient(api_app_factory(member_user)) as client:
        response = client.get(
            f"/api/v1/projects/{uuid4()}/tasks/{uuid4()}"
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "task_or_project_not_found"


def test_task_validation_rejects_invalid_priority(
    api_app_factory,
    member_user: UserDO,
) -> None:
    with TestClient(api_app_factory(member_user)) as client:
        response = client.post(
            f"/api/v1/projects/{uuid4()}/tasks",
            json={"title": "错误优先级", "priority": 6},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
