from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.v1.plan_controller import get_plan_service
from app.schemas.plan_vo import PlanInfoVO, PlanProposalVO, PlanResultVO
from fastapi.testclient import TestClient
from test_plan_schema import proposal_data


def test_planning_requires_member(api_app_factory, reviewer_user):
    path = f"/api/v1/projects/{uuid4()}/planning"
    for user, status in [(None, 401), (reviewer_user, 403)]:
        with TestClient(api_app_factory(user)) as client:
            assert client.get(path).status_code == status
            assert (
                client.post(path + "/proposals", json={"goal": "实现订单"}).status_code
                == status
            )


@pytest.mark.parametrize(
    "body",
    [
        {"goal": " "},
        {"goal": "字" * 2001},
        {"goal": "实现订单", "user_id": "伪造身份"},
        {"goal": "实现订单", "approved": True},
    ],
)
def test_planning_rejects_invalid_input(api_app_factory, member_user, body):
    app = api_app_factory(member_user)
    planner = AsyncMock()
    app.dependency_overrides[get_plan_service] = lambda: planner
    with TestClient(app) as client:
        result = client.post(
            f"/api/v1/projects/{uuid4()}/planning/proposals", json=body
        )
    assert result.status_code == 422
    planner.create.assert_not_awaited()


def test_planning_contract_never_reports_persisted(api_app_factory, member_user):
    project = uuid4()
    app = api_app_factory(member_user)
    planner = AsyncMock()
    planner.info.return_value = PlanInfoVO(
        mode="mock", configured=True, ready_documents=1, task_count=2
    )
    planner.create.return_value = PlanResultVO(
        mode="mock",
        proposal=PlanProposalVO.model_validate(proposal_data()),
        sources=[],
        tool_calls=[],
        board_task_count=2,
    )
    app.dependency_overrides[get_plan_service] = lambda: planner
    with TestClient(app) as client:
        path = f"/api/v1/projects/{project}/planning"
        assert client.get(path).json()["task_count"] == 2
        result = client.post(path + "/proposals", json={"goal": "  实现订单  "})
    assert result.status_code == 200
    assert result.json()["persisted"] is False
    assert result.json()["proposal"]["tasks"][1]["dependencies"] == ["T1"]
    assert planner.create.await_args.args == (member_user.id, project, "实现订单")
