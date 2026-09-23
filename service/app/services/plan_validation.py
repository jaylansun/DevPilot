"""把模型校验异常转换为固定规则提示，不回显模型参数、原文或异常正文。"""

from langchain.agents.structured_output import (
    MultipleStructuredOutputsError,
    StructuredOutputValidationError,
)
from pydantic import ValidationError

FIELDS = frozenset(
    {
        "summary",
        "assumptions",
        "risks",
        "tasks",
        "draft_id",
        "title",
        "description",
        "priority",
        "acceptance_criteria",
        "dependencies",
        "source_ids",
    }
)
LABELS = {
    "summary": "方案摘要",
    "assumptions": "假设",
    "risks": "风险",
    "tasks": "任务",
    "draft_id": "草案编号",
    "title": "标题",
    "description": "说明",
    "priority": "优先级",
    "acceptance_criteria": "验收标准",
    "dependencies": "前置依赖",
    "source_ids": "引用编号",
}
RULES = {
    "missing": "缺少必填字段",
    "int_type": "必须使用 JSON 整数，不能使用字符串或布尔值",
    "int_parsing": "必须使用 JSON 整数",
    "string_type": "必须使用字符串，不能使用数组或对象",
    "list_type": "必须使用数组，无内容时使用空数组",
    "string_pattern_mismatch": "草案编号必须为 T1 至 T12",
    "extra_forbidden": "不能添加约定以外的字段",
    "string_too_long": "文字长度超过字段上限",
    "string_too_short": "内容不能为空",
    "too_long": "条目数量超过字段上限",
    "too_short": "条目数量不足",
    "greater_than_equal": "数值低于字段下限",
    "less_than_equal": "数值超过字段上限",
    "self_dependency": "任务不能依赖自身",
    "duplicate_dependencies": "前置依赖不能重复",
    "duplicate_sources": "引用编号不能重复",
    "duplicate_id": "草案编号不能重复",
    "duplicate_title": "任务标题不能重复",
    "unknown_dependency": "前置依赖只能引用本方案内已有的 T 编号，不能引用看板任务编号或标题",
    "dependency_cycle": "任务依赖形成了循环，需要调整先后顺序",
    "multiple_outputs": "只能提交一个完整的 PlanProposalVO",
    "schema_violation": "字段结构或任务依赖不符合约定",
}
CUSTOM_ERRORS = {
    "前置任务编号不能重复": "duplicate_dependencies",
    "任务不能依赖自身": "self_dependency",
    "文档引用编号不能重复": "duplicate_sources",
    "任务草案编号不能重复": "duplicate_id",
    "任务标题不能重复": "duplicate_title",
    "前置任务必须引用本方案中存在的编号": "unknown_dependency",
    "任务依赖不能形成循环": "dependency_cycle",
}


def plan_validation_issues(exc: Exception) -> list[dict[str, str]]:
    if isinstance(exc, MultipleStructuredOutputsError):
        return [
            {
                "field": "proposal",
                "type": "multiple_outputs",
                "message": RULES["multiple_outputs"],
            }
        ]
    pending, seen = [exc], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ValidationError):
            issues = []
            for error in current.errors(
                include_input=False, include_context=False, include_url=False
            )[:8]:
                kind = error["type"]
                if kind == "value_error":
                    kind = CUSTOM_ERRORS.get(
                        error["msg"].removeprefix("Value error, "), "schema_violation"
                    )
                if kind not in RULES:
                    kind = "schema_violation"
                location = [
                    str(part)
                    if isinstance(part, int)
                    else part
                    if part in FIELDS
                    else "unknown"
                    for part in error["loc"][:6]
                ]
                issues.append(
                    {
                        "field": ".".join(location) or "proposal",
                        "type": kind,
                        "message": RULES[kind],
                    }
                )
            return issues
        pending.extend(
            nested
            for attr in ("source", "__cause__", "__context__")
            if isinstance(nested := getattr(current, attr, None), Exception)
        )
    return [
        {
            "field": "proposal",
            "type": "schema_violation",
            "message": RULES["schema_violation"],
        }
    ]


def plan_repair_feedback(exc: Exception) -> str:
    issues = plan_validation_issues(exc)
    detail = "；".join(f"{item['field']}：{item['message']}" for item in issues)
    return (
        f"方案未通过校验：{detail}。{_missing_dependency_feedback(exc)}"
        "请依据已读取的资料纠正，重新提交一个完整的 PlanProposalVO，不再调用读取工具。"
        "提交前检查所有字段类型，并逐项确认 dependencies 的每个编号都对应本次 tasks 中的任务，"
        "不能依赖自身或形成循环。"
    )


def _missing_dependency_feedback(exc: Exception) -> str:
    """字段类型错误会阻止整方案校验；仍提示同时存在的悬空依赖，不改写模型结果。"""
    if not isinstance(exc, StructuredOutputValidationError):
        return ""
    allowed = {f"T{number}" for number in range(1, 13)}
    for call in exc.ai_message.tool_calls:
        if call["name"] != "PlanProposalVO":
            continue
        tasks = call["args"].get("tasks")
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 12:
            continue
        ids = {
            value
            for task in tasks
            if isinstance(task, dict)
            and isinstance(value := task.get("draft_id"), str)
            and value in allowed
        }
        missing = []
        for index, task in enumerate(tasks):
            dependencies = task.get("dependencies") if isinstance(task, dict) else None
            if not isinstance(dependencies, list):
                continue
            for value in dependencies[:11]:
                # 只允许固定 T 编号进入提示，不回显任意参数或用户文字。
                if isinstance(value, str) and value in allowed and value not in ids:
                    missing.append(f"tasks.{index}.dependencies 引用了不存在的 {value}")
        if missing:
            return "同时发现：" + "；".join(missing[:8]) + "。"
    return ""


def plan_error_message(issues: list[dict[str, str]]) -> str:
    issue = issues[0]
    label = " / ".join(
        LABELS.get(part, "") for part in issue["field"].split(".") if part in LABELS
    )
    detail = f"{label}：" if label else ""
    message = {
        "int_type": "数值格式不正确，应为整数",
        "int_parsing": "数值格式不正确，应为整数",
        "string_type": "文字格式不正确",
        "list_type": "列表格式不正确",
        "unknown_dependency": "依赖引用了本方案以外的任务",
        "multiple_outputs": "模型返回了多份方案，需要合并为一份",
    }.get(issue["type"], issue["message"])
    return f"模型生成的任务方案未通过校验：{detail}{message}。请重试或缩小规划范围。"
