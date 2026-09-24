import json

import httpx
import pytest
from app.schemas.workflow_vo import GapReportVO, TaskLookupVO, WorkflowIntentVO
from app.services.workflow_model_service import WorkflowModelService
from langchain_openai import ChatOpenAI
from test_rag_model import configuration


@pytest.mark.parametrize(
    "model,base_url,thinking",
    [
        ("mimo-v2.5", "https://api.xiaomimimo.com/v1", {"type": "disabled"}),
        ("mimo-v2.5-pro", "https://api.xiaomimimo.com/v1/", {"type": "disabled"}),
        ("fixture", "https://api.xiaomimimo.com/v1", None),
        ("mimo-v2.5", "https://fixture.invalid/v1", None),
        ("mimo-v2.5", "https://api.xiaomimimo.com.fixture.invalid/v1", None),
    ],
)
async def test_all_workflow_model_calls_send_expected_provider_options(
    monkeypatch, model, base_url, thinking
):
    replies = {
        "WorkflowIntentVO": {"intent": "requirement_check"},
        "GapReportVO": {
            "summary": "资料不足，需要补充文档。",
            "covered": [],
            "missing": [],
            "questions": [],
            "reviewed_source_ids": [1],
            "insufficient_evidence": True,
        },
        "TaskLookupVO": {"summary": "没有匹配任务。", "task_ids": []},
    }
    called = []

    def respond(request):
        body = json.loads(request.content)
        assert body["model"] == model
        assert body.get("thinking") == thinking
        assert not body.get("stream", False)
        name = body["tools"][0]["function"]["name"]
        called.append(name)
        return httpx.Response(
            200,
            json={
                "id": "workflow-test",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "test-call",
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(replies[name]),
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(
            "app.services.workflow_model_service.ChatOpenAI",
            lambda **kwargs: ChatOpenAI(**kwargs, http_async_client=client),
        )
        service = WorkflowModelService(
            configuration(
                ai_mode="live",
                model_name=model,
                llm_base_url=base_url,
                llm_api_key="fixture-key",
            )
        )
        assert isinstance(await service.classify("检查遗漏"), WorkflowIntentVO)
        assert isinstance(
            await service.report("检查遗漏", [], {"tasks": []}), GapReportVO
        )
        assert isinstance(await service.lookup("查任务", {"tasks": []}), TaskLookupVO)
    assert called == list(replies)
