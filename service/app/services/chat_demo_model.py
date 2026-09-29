"""离线演示模型也经过正式 Agent/工具/检查点流程，不调用外部模型。"""

import json
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class DemoChatModel(BaseChatModel):
    summarizing: bool = False

    @property
    def _llm_type(self):
        return "devpilot-chat-demo"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.summarizing:
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="演示模式保留的历史片段：\n"
                            + str(messages[-1].content)[-2800:]
                        )
                    )
                ]
            )
        latest = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        question = str(messages[latest].content)
        output = next(
            (m for m in reversed(messages[latest + 1 :]) if isinstance(m, ToolMessage)),
            None,
        )
        greeting = question.casefold().strip("！!。.?？ ")
        result = {
            "answer": "你好！当前是演示模式；会话会自动保存，启用真实模型后可进行自然的连续对话。",
            "basis": "general",
            "source_ids": [],
            "task_ids": [],
            "insufficient_evidence": False,
        }
        name, args = "ChatCompletion", result
        if output:
            data = json.loads(output.content)
            result["basis"] = "project"
            if output.name == "read_task_board":
                result["answer"] = (
                    f"演示模式读取到 {data['total']} 项任务，未调用模型进行语义筛选。请查看下方实际看板记录。"
                )
                result["task_ids"] = [task["id"] for task in data["tasks"]]
            else:
                result["source_ids"] = [
                    source["source_id"] for source in data["sources"]
                ]
                result["insufficient_evidence"] = not bool(result["source_ids"])
                result["answer"] = (
                    (
                        "演示模式未调用大模型；以下是实际检索到的资料，请展开来源查看原文："
                        + " ".join(f"[{value}]" for value in result["source_ids"])
                    )
                    if result["source_ids"]
                    else "没有检索到足够的项目资料，请上传相关文档后再试。当前为演示模式。"
                )
        elif greeting not in {
            "你好",
            "您好",
            "嗨",
            "hello",
            "hi",
            "谢谢",
            "讲个笑话",
            "聊聊天",
        }:
            name = (
                "read_task_board"
                if "任务" in question or "看板" in question
                else "search_documents"
            )
            args = {} if name == "read_task_board" else {"query": question}
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": name,
                                "args": args,
                                "id": str(uuid4()),
                                "type": "tool_call",
                            }
                        ],
                    )
                )
            ]
        )
