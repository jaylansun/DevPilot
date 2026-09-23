from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.v1.rag_controller import get_rag_service
from app.schemas.rag_vo import RagAnswerVO, RagInfoVO
from fastapi.testclient import TestClient


def test_rag_requires_member_and_login(api_app_factory, reviewer_user):
    path = f"/api/v1/projects/{uuid4()}/knowledge"
    for user, status in [(None, 401), (reviewer_user, 403)]:
        with TestClient(api_app_factory(user)) as client:
            assert client.get(path).status_code == status
            assert (
                client.post(
                    path + "/questions", json={"question": "订单规则？"}
                ).status_code
                == status
            )


@pytest.mark.parametrize(
    "body",
    [
        {"question": "   "},
        {"question": "字" * 2001},
        {"question": "订单规则？", "user_id": str(uuid4())},
    ],
)
def test_rag_question_validation(api_app_factory, member_user, body):
    app = api_app_factory(member_user)
    service = AsyncMock()
    app.dependency_overrides[get_rag_service] = lambda: service
    with TestClient(app) as client:
        result = client.post(
            f"/api/v1/projects/{uuid4()}/knowledge/questions", json=body
        )
    assert result.status_code == 422
    service.answer.assert_not_awaited()


def test_rag_contract_and_server_side_identity(api_app_factory, member_user):
    app = api_app_factory(member_user)
    project = uuid4()
    service = AsyncMock()
    service.info.return_value = RagInfoVO(
        mode="mock", configured=True, ready_documents=1
    )
    service.answer.return_value = RagAnswerVO(
        answer="资料不足", sources=[], status="insufficient_evidence", mode="mock"
    )
    app.dependency_overrides[get_rag_service] = lambda: service
    with TestClient(app) as client:
        base = f"/api/v1/projects/{project}/knowledge"
        assert client.get(base).json() == {
            "mode": "mock",
            "configured": True,
            "ready_documents": 1,
        }
        result = client.post(base + "/questions", json={"question": "  订单规则？  "})
    assert result.status_code == 200
    assert result.json()["sources"] == []
    assert service.answer.await_args.args == (member_user.id, project, "订单规则？")
