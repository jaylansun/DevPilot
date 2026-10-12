"""工件历史只帮助理解追问，不作为当前项目事实或来源编号。"""

import json
import re

from app.schemas.chat_vo import ChatAnswerVO, ChatCheckArtifactVO, ChatPlanArtifactVO


def without_source_numbers(text: str) -> str:
    return re.sub(r"\[(\d+)\]", "", text).strip()


def artifact_summary(artifact):
    if isinstance(artifact, ChatPlanArtifactVO):
        return {
            "type": artifact.type,
            "goal": artifact.goal,
            "summary": without_source_numbers(artifact.result.proposal.summary),
            "tasks": [
                {"draft_id": task.draft_id, "title": without_source_numbers(task.title)}
                for task in artifact.result.proposal.tasks
            ],
            "mode": artifact.result.mode,
        }
    if isinstance(artifact, ChatCheckArtifactVO):
        report = artifact.result.report
        return {
            "type": artifact.type,
            "summary": without_source_numbers(artifact.result.answer),
            "missing": [
                without_source_numbers(item.requirement) for item in report.missing
            ]
            if report
            else [],
            "questions": [
                without_source_numbers(item.question) for item in report.questions
            ]
            if report
            else [],
            "covered_count": len(report.covered) if report else 0,
            "status": artifact.result.status,
            "mode": artifact.result.mode,
        }
    raise TypeError("不支持的聊天工件")


def context_answer(result: ChatAnswerVO) -> str:
    """检查点和数据库恢复共用同一份工件概要，编号仅在原工件内有效。"""
    if not result.artifacts:
        return result.answer
    summaries = []
    for artifact in result.artifacts:
        summary = artifact_summary(artifact)
        summary["summary"] = summary["summary"][:1000]
        if summary["type"] == "requirement_check":
            summary["missing"] = [item[:160] for item in summary["missing"]]
            summary["questions"] = [item[:160] for item in summary["questions"]]
        summaries.append(summary)
    return (
        result.answer
        + "\n\n历史工件概要（仅用于理解追问；不是当前项目依据，后续业务须重新读取）：\n"
        + json.dumps(summaries, ensure_ascii=False)
    )
