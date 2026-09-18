from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from app.errors import ApiError
from app.schemas.rag_vo import RagSourceVO
from app.schemas.workflow_qo import WorkflowIntent
from app.schemas.workflow_vo import (
    GapReportVO,
    TaskEvidenceVO,
    TaskLookupVO,
    WorkflowResultVO,
    WorkflowScopeVO,
)
from app.services.planning_read_service import PlanningReadService
from app.services.rag_service import UNKNOWN_ANSWER, build_answer


@dataclass(frozen=True)
class WorkflowContext:
    owner_id: UUID
    project_id: UUID
    documents: PlanningReadService
    board: PlanningReadService


class WorkflowState(TypedDict, total=False):
    message: str
    requested_intent: str
    intent: WorkflowIntent
    sources: list[RagSourceVO]
    board: dict
    result: WorkflowResultVO


def validate_report(
    report: GapReportVO, sources: list[RagSourceVO], board: dict
) -> None:
    available = {source.source_id for source in sources}
    reviewed = report.reviewed_source_ids
    if set(reviewed) != available or len(reviewed) != len(set(reviewed)):
        raise ApiError(
            502, "invalid_workflow_sources", "报告没有准确列出本次检查依据，请重试"
        )
    for item in [*report.covered, *report.missing, *report.questions]:
        if not set(item.source_ids) <= available or len(item.source_ids) != len(
            set(item.source_ids)
        ):
            raise ApiError(
                502, "invalid_workflow_sources", "报告包含无效的文档引用，请重试"
            )
    task_ids = {UUID(task["id"]) for task in board["tasks"]}
    for item in report.covered:
        if not set(item.task_ids) <= task_ids or len(item.task_ids) != len(
            set(item.task_ids)
        ):
            raise ApiError(
                502, "invalid_workflow_tasks", "报告包含不属于本次看板的任务，请重试"
            )


class WorkflowGraph:
    """显式路由、并行读取和汇合；仅在单次请求中保留 State。"""

    def __init__(self, settings, model_service, rag_model_service):
        self.settings = settings
        self.model = model_service
        self.rag_model = rag_model_service
        builder = StateGraph(WorkflowState, context_schema=WorkflowContext)
        for name, node in {
            "classify_intent": self.classify,
            "retrieve_knowledge": self.retrieve,
            "answer_knowledge": self.answer_knowledge,
            "load_lookup_board": self.read_board,
            "answer_lookup": self.answer_lookup,
            "retrieve_documents": self.retrieve,
            "load_task_board": self.read_board,
            "generate_report": self.generate_report,
            "clarify": self.clarify,
            "validate_result": self.validate_result,
        }.items():
            builder.add_node(name, node)
        builder.add_edge(START, "classify_intent")
        builder.add_conditional_edges(
            "classify_intent",
            self.route,
            [
                "retrieve_knowledge",
                "load_lookup_board",
                "retrieve_documents",
                "load_task_board",
                "clarify",
            ],
        )
        builder.add_edge("retrieve_knowledge", "answer_knowledge")
        builder.add_edge("load_lookup_board", "answer_lookup")
        # 等待两个独立节点都完成才生成报告，避免用不完整 State 生成结论。
        builder.add_edge(["retrieve_documents", "load_task_board"], "generate_report")
        for node in ("answer_knowledge", "answer_lookup", "generate_report", "clarify"):
            builder.add_edge(node, "validate_result")
        builder.add_edge("validate_result", END)
        self.graph = builder.compile()

    async def classify(self, state: WorkflowState):
        requested = state["requested_intent"]
        intent = (
            (await self.model.classify(state["message"])).intent
            if requested == "auto"
            else requested
        )
        return {"intent": intent}

    @staticmethod
    def route(state: WorkflowState) -> list[str]:
        return {
            "knowledge_question": ["retrieve_knowledge"],
            "task_lookup": ["load_lookup_board"],
            "requirement_check": ["retrieve_documents", "load_task_board"],
            "clarify": ["clarify"],
        }[state["intent"]]

    async def retrieve(self, state: WorkflowState, runtime: Runtime[WorkflowContext]):
        context = runtime.context
        await context.documents.search_documents(
            context.owner_id, context.project_id, state["message"]
        )
        return {"sources": list(context.documents.sources)}

    async def read_board(self, state: WorkflowState, runtime: Runtime[WorkflowContext]):
        context = runtime.context
        board = await context.board.read_task_board(
            context.owner_id, context.project_id
        )
        return {"board": board}

    def result(self, state, context, *, status, answer, report=None, tasks=None):
        sources = state.get("sources", [])
        board = state.get("board")
        return WorkflowResultVO(
            intent=state["intent"],
            mode=self.settings.ai_mode,
            status=status,
            answer=answer,
            report=report,
            tasks=tasks or [],
            sources=sources,
            tool_calls=[*context.documents.tool_calls, *context.board.tool_calls],
            scope=WorkflowScopeVO(
                ready_documents=[
                    {"document_id": key, "filename": value}
                    for key, value in context.documents.ready_documents.items()
                ],
                retrieved_source_count=len(sources),
                document_search_performed="sources" in state,
                board_read=board is not None,
                tasks=board["tasks"] if board else [],
                task_details_truncated=board["truncated"] if board else False,
                limitation="文档仅按本次输入检索最多 4 段，每段最多 400 字符，未逐份检查全文；未就绪文档不参与检索。看板最多读取 100 项，说明与验收标准各保留前 400 字符。有对应任务不代表功能已经实现。",
            ),
        )

    async def generate_report(
        self, state: WorkflowState, runtime: Runtime[WorkflowContext]
    ):
        sources, board = state["sources"], state["board"]
        report = None
        if not sources:
            status = "insufficient_evidence"
            answer = "没有检索到可用于对照的需求片段，无法判断是否遗漏。请上传资料、等待索引就绪，或缩小检查范围。"
        elif self.settings.ai_mode == "mock":
            status = "demo"
            answer = "已读取真实文档片段和任务看板。演示模式未调用聊天模型，不判断需求覆盖或遗漏；请展开检查范围自行核对。"
        else:
            report = await self.model.report(state["message"], sources, board)
            report = GapReportVO.model_validate(report.model_dump())
            validate_report(report, sources, board)
            status = (
                "insufficient_evidence" if report.insufficient_evidence else "reviewed"
            )
            answer = report.summary
        return {
            "result": self.result(
                state, runtime.context, status=status, answer=answer, report=report
            )
        }

    async def answer_knowledge(
        self, state: WorkflowState, runtime: Runtime[WorkflowContext]
    ):
        sources = state["sources"]
        if not sources:
            status, answer = "insufficient_evidence", UNKNOWN_ANSWER
        else:
            response = await self.rag_model.answer(state["message"], sources)
            grounded = build_answer(response, sources, self.settings.ai_mode)
            status, answer = grounded.status, grounded.answer
            if status == "answered" and self.settings.ai_mode == "mock":
                status = "demo"
        return {
            "result": self.result(state, runtime.context, status=status, answer=answer)
        }

    async def answer_lookup(
        self, state: WorkflowState, runtime: Runtime[WorkflowContext]
    ):
        response = await self.model.lookup(state["message"], state["board"])
        response = TaskLookupVO.model_validate(response.model_dump())
        available = {UUID(task["id"]): task for task in state["board"]["tasks"]}
        if not set(response.task_ids) <= available.keys() or len(
            response.task_ids
        ) != len(set(response.task_ids)):
            raise ApiError(
                502, "invalid_workflow_tasks", "查询返回了无效的任务编号，请重试"
            )
        tasks = [
            TaskEvidenceVO.model_validate(available[task_id])
            for task_id in response.task_ids
        ]
        return {
            "result": self.result(
                state,
                runtime.context,
                status="answered",
                answer=response.summary,
                tasks=tasks,
            )
        }

    async def clarify(self, state: WorkflowState, runtime: Runtime[WorkflowContext]):
        return {
            "result": self.result(
                state,
                runtime.context,
                status="clarification_needed",
                answer="这里支持需求缺口检查、文档问答和已有任务查询。请选择用途并说明范围；如需修改任务，请到任务看板手工操作。",
            )
        }

    async def validate_result(
        self, state: WorkflowState, runtime: Runtime[WorkflowContext]
    ):
        context = runtime.context
        # 两个读取器共享同一初始基线；最后复核可发现模型计算期间的资料或任务变更。
        await context.documents.assert_unchanged(context.owner_id, context.project_id)
        return {"result": WorkflowResultVO.model_validate(state["result"].model_dump())}
