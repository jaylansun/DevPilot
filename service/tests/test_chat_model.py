import json

import httpx
import pytest
from langchain_core.messages import (
    AIMessageChunk,
)
from test_chat import ask, finish, service
from test_planning_tools import planning_context as _planning_context

from app.errors import ApiError
from app.schemas.chat_qo import ChatRequestQO
from app.services.chat_model_service import ChatModelService
from app.services.chat_service import ChatService

planning_context = _planning_context
from test_rag_model import configuration
from test_streaming import RecordingPublisher


@pytest.mark.parametrize("streaming", [False, True])
async def test_real_model_wire_contract_tool_selection_and_incremental_answer(
    monkeypatch, streaming, planning_context
):
    from langchain_openai import ChatOpenAI

    calls = []
    final = {
        "answer": "退款期限为七天。[1]",
        "basis": "project",
        "source_ids": [1],
        "task_ids": [],
        "insufficient_evidence": False,
    }

    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body["tool_choice"] == "required"
        tools = {tool["function"]["name"]: tool["function"] for tool in body["tools"]}
        assert set(tools) == {"search_documents", "read_task_board", "ChatCompletion"}
        assert set(tools["search_documents"]["parameters"]["properties"]) == {"query"}
        assert tools["read_task_board"]["parameters"]["properties"] == {}
        name = "search_documents" if len(calls) == 1 else "ChatCompletion"
        args = json.dumps(
            {"query": "退款期限"} if len(calls) == 1 else final, ensure_ascii=False
        )
        call = {
            "id": f"call-{len(calls)}",
            "type": "function",
            "function": {"name": name, "arguments": args},
        }
        base = {"id": "chat-test", "created": 1, "model": "test-model"}
        if not streaming:
            return httpx.Response(
                200,
                json={
                    **base,
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [call],
                            },
                        }
                    ],
                },
            )
        frames = []
        for offset in range(0, len(args), 4):
            delta = {"index": 0, "function": {"arguments": args[offset : offset + 4]}}
            if offset == 0:
                delta.update({"id": call["id"], "type": "function"})
                delta["function"]["name"] = name
            frames.append(
                {
                    **base,
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": None,
                            "delta": {"role": "assistant", "tool_calls": [delta]},
                        }
                    ],
                }
            )
        frames.append(
            {
                **base,
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "finish_reason": "tool_calls", "delta": {}}],
            }
        )
        content = (
            "".join(
                "data: " + json.dumps(frame, ensure_ascii=False) + "\n\n"
                for frame in frames
            )
            + "data: [DONE]\n\n"
        )
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, content=content
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(
            "langchain_openai.ChatOpenAI",
            lambda **kwargs: ChatOpenAI(**kwargs, http_async_client=client),
        )
        model = ChatModelService(
            configuration(
                ai_mode="live",
                model_name="test-model",
                llm_api_key="synthetic-test-key",
                llm_base_url="https://example.invalid/v1",
            )
        )
        events = RecordingPublisher()
        factory, owner, project, *_ = planning_context
        chat = ChatService(model.settings, planning_context[5], factory, model)
        result = await chat.answer(
            owner,
            project,
            ChatRequestQO(question="项目退款期限？"),
            events=events,
            streaming=streaming,
        )
        assert result.answer == final["answer"]
        tokens = [item["text"] for item in events.events if item["type"] == "token"]
        if streaming:
            assert len(tokens) > 1
            assert "".join(tokens) == final["answer"]
        else:
            assert tokens == []
    assert calls[1]["messages"][-1]["role"] == "tool"


async def test_incomplete_streamed_tool_arguments_are_rejected(planning_context):
    arguments = json.dumps(finish().tool_calls[0]["args"], ensure_ascii=False)[:-1]
    response = AIMessageChunk(
        content="",
        tool_call_chunks=[
            {
                "index": 0,
                "id": "broken",
                "name": "ChatCompletion",
                "args": arguments,
            }
        ],
    )
    chat = service(planning_context, response)
    with pytest.raises(ApiError) as error:
        await ask(chat, planning_context)
    assert error.value.code == "invalid_chat"
