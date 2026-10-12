"""聊天业务工具生成本轮工件；持久保存由会话提交事务负责。"""

from app.errors import ApiError
from app.schemas.chat_vo import ChatCheckArtifactVO, ChatPlanArtifactVO
from app.schemas.plan_vo import PlanResultVO
from app.schemas.workflow_qo import WorkflowRequestQO
from app.schemas.workflow_vo import WorkflowResultVO
from app.services.chat_context_service import artifact_summary, without_source_numbers
from app.services.planning_read_service import PlanningReadService
from app.services.run_events import trace
from app.services.workflow_graph import validate_report


def claim_business_call(context, name, service):
    if service is None:
        raise ApiError(503, "chat_capability_unavailable", "当前聊天尚未启用此能力")
    # 无 await 的检查与登记同时保护模型并行调用和显式模式；失败也不重复调用。
    if name in context.business_calls or len(context.business_calls) >= 2:
        raise ApiError(502, "chat_tool_limit", "每轮最多生成一次草案和一次需求检查")
    context.business_calls.add(name)


async def begin_artifact_read(context):
    reader = PlanningReadService(
        context.reader.session_factory,
        context.reader.index_service,
        context.reader.min_score,
    )
    await reader.assert_unchanged(context.owner, context.project)
    return reader


def validate_plan(result):
    result = PlanResultVO.model_validate(result.model_dump())
    available = {source.source_id for source in result.sources}
    selected = {value for task in result.proposal.tasks for value in task.source_ids}
    executed = {call.name for call in result.tool_calls}
    if (
        result.persisted
        or not available
        or len(available) != len(result.sources)
        or not selected
        or not selected <= available
        or not {"search_documents", "read_task_board"} <= executed
    ):
        raise ApiError(502, "invalid_plan", "任务草案或资料依据不符合要求，请重试")
    return result


def validate_check(result):
    result = WorkflowResultVO.model_validate(result.model_dump())
    available = {source.source_id for source in result.sources}
    if (
        result.intent != "requirement_check"
        or result.status not in {"reviewed", "insufficient_evidence", "demo"}
        or len(available) != len(result.sources)
        or not result.scope.document_search_performed
        or not result.scope.board_read
        or result.scope.retrieved_source_count != len(result.sources)
        or result.status == "reviewed"
        and result.report is None
    ):
        raise ApiError(502, "invalid_workflow_result", "需求检查结果不符合要求，请重试")
    if result.report is not None:
        validate_report(
            result.report,
            result.sources,
            {"tasks": [task.model_dump(mode="json") for task in result.scope.tasks]},
        )
    return result


async def run_task_planning(context, goal):
    claim_business_call(context, "generate_task_plan", context.planner)
    async with trace(context.events, "generate_task_plan", kind="tool"):
        reader = await begin_artifact_read(context)
        result = validate_plan(
            await context.planner.create(
                context.owner, context.project, goal, events=context.events
            )
        )
        await reader.assert_unchanged(context.owner, context.project)
        artifact = ChatPlanArtifactVO(goal=goal, result=result)
        artifact._document_hashes = reader.document_hashes_for_sources(result.sources)
        context.artifact_readers.append(reader)
        context.artifacts.append(artifact)
        context.reader.tool_calls.append(
            {
                "name": "generate_task_plan",
                "status": "success",
                "item_count": len(result.proposal.tasks),
            }
        )
        return {
            **artifact_summary(artifact),
            "artifact_type": artifact.type,
            "summary": without_source_numbers(result.proposal.summary),
            "task_count": len(result.proposal.tasks),
            "mode": result.mode,
            "persisted": False,
            "evidence_note": "草案及其资料依据在独立结果中展示；正文不要使用工件内的来源编号。此工具未保存草案或创建任务。",
        }


async def run_requirement_check(context, scope):
    claim_business_call(context, "check_requirements", context.workflow)
    async with trace(context.events, "check_requirements", kind="tool"):
        reader = await begin_artifact_read(context)
        result = validate_check(
            await context.workflow.run(
                context.owner,
                context.project,
                WorkflowRequestQO(message=scope, intent="requirement_check"),
                events=context.events,
            )
        )
        await reader.assert_unchanged(context.owner, context.project)
        reader.document_hashes_for_sources(result.sources)
        artifact = ChatCheckArtifactVO(result=result)
        context.artifact_readers.append(reader)
        context.artifacts.append(artifact)
        context.reader.tool_calls.append(
            {
                "name": "check_requirements",
                "status": "success" if result.sources else "empty",
                "item_count": len(result.sources),
            }
        )
        return {
            **artifact_summary(artifact),
            "artifact_type": artifact.type,
            "summary": without_source_numbers(result.answer),
            "status": result.status,
            "mode": result.mode,
            "covered_count": len(result.report.covered) if result.report else 0,
            "missing_count": len(result.report.missing) if result.report else 0,
            "question_count": len(result.report.questions) if result.report else 0,
            "evidence_note": "报告及其资料依据在独立结果中展示；正文不要使用工件内的来源编号。仅检查检索片段，有对应任务不代表已实现。",
        }
