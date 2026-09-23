"""持久审批 Graph：复用已保存草案或生成方案；人工批准后才写入任务。"""

from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.services.run_events import EventPublisher, trace


@dataclass(frozen=True)
class ApprovalContext:
    conversation_id: UUID
    owner_id: UUID
    project_id: UUID
    events: EventPublisher
    reviewer_id: UUID | None = None


class ApprovalState(TypedDict, total=False):
    goal: str
    plan: dict
    approval_id: str
    decision: dict
    result: dict


class ApprovalGraph:
    def __init__(self, service, checkpointer):
        self.service = service
        builder = StateGraph(ApprovalState, context_schema=ApprovalContext)
        builder.add_node("generate_plan", self.generate_plan)
        builder.add_node("submit_approval", self.submit_approval)
        builder.add_node("await_approval", self.await_approval)
        builder.add_node("apply_decision", self.apply_decision)
        builder.add_conditional_edges(
            START,
            lambda state: "submit_approval" if state.get("plan") else "generate_plan",
            {"submit_approval": "submit_approval", "generate_plan": "generate_plan"},
        )
        builder.add_edge("generate_plan", "submit_approval")
        builder.add_edge("submit_approval", "await_approval")
        builder.add_edge("await_approval", "apply_decision")
        builder.add_edge("apply_decision", END)
        self.graph = builder.compile(checkpointer=checkpointer)

    async def generate_plan(
        self, state: ApprovalState, runtime: Runtime[ApprovalContext]
    ):
        plan = await self.service.generate(runtime.context, state["goal"])
        return {"plan": plan.model_dump(mode="json")}

    async def submit_approval(
        self, state: ApprovalState, runtime: Runtime[ApprovalContext]
    ):
        async with trace(runtime.context.events, "submit_approval"):
            approval = await self.service.record_submission(
                runtime.context, state["plan"]
            )
        return {"approval_id": str(approval.id)}

    async def await_approval(self, state: ApprovalState):
        # 恢复时本节点从头执行，因此 interrupt 前不写库、不发重复事件。
        decision = interrupt({"approval_id": state["approval_id"]})
        return {"decision": decision}

    async def apply_decision(
        self, state: ApprovalState, runtime: Runtime[ApprovalContext]
    ):
        async with trace(runtime.context.events, "apply_approval"):
            result = await self.service.persist_decision(
                runtime.context, state["decision"]
            )
        return {"result": result.model_dump(mode="json")}
