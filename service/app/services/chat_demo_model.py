"""离线演示模型也经过正式 Agent/工具/检查点流程，不调用外部模型。"""

import json
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class DemoChatModel(BaseChatModel):
    summarizing: bool = False
    available_tool_names: tuple[str, ...] = ()

    @property
    def _llm_type(self):
        return "devpilot-chat-demo"

    def bind_tools(self, tools, **kwargs):
        names = []
        for bound_tool in tools:
            if isinstance(bound_tool, dict):
                name = bound_tool.get("function", bound_tool).get("name")
            else:
                name = getattr(
                    bound_tool, "name", getattr(bound_tool, "__name__", None)
                )
            if name:
                names.append(name)
        return self.model_copy(update={"available_tool_names": tuple(names)})

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
            if output.name in {"generate_task_plan", "check_requirements"}:
                result["answer"] = (
                    data["summary"]
                    + "\n\n当前为演示模式，请展开结果查看实际资料、范围及演示限制。"
                )
                result["insufficient_evidence"] = (
                    data.get("status") == "insufficient_evidence"
                )
            elif output.name == "read_task_board":
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
            if "check_requirements" in self.available_tool_names and any(
                word in question for word in ("检查", "遗漏", "覆盖", "缺口", "对照")
            ):
                name, args = "check_requirements", {"scope": question}
            elif "generate_task_plan" in self.available_tool_names and any(
                word in question for word in ("规划", "拆解", "拆分", "草案")
            ):
                name, args = "generate_task_plan", {"goal": question}
            else:
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
