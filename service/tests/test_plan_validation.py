import pytest
from app.schemas.plan_vo import PlanProposalVO
from app.services.plan_validation import (
    plan_error_message,
    plan_repair_feedback,
    plan_validation_issues,
)
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.messages import AIMessage
from pydantic import ValidationError
from test_plan_schema import proposal_data


@pytest.mark.parametrize(
    "change,expected",
    [
        ("priority", "int_type"),
        ("cycle", "dependency_cycle"),
        ("external", "unknown_dependency"),
        ("extra", "extra_forbidden"),
    ],
)
def test_validation_feedback_keeps_only_safe_fields_and_fixed_rules(change, expected):
    data = proposal_data()
    secret = "private-model-output-never-log"
    if change == "priority":
        data["tasks"][0]["priority"] = secret
    elif change == "cycle":
        data["tasks"][0]["dependencies"] = ["T2"]
    elif change == "external":
        data["tasks"][0]["dependencies"] = ["T9"]
    else:
        data[secret] = secret
    with pytest.raises(ValidationError) as error:
        PlanProposalVO.model_validate(data)
    wrapper = ValueError(secret)
    wrapper.__cause__ = error.value
    outer = StructuredOutputValidationError(
        "PlanProposalVO", wrapper, AIMessage(content=secret)
    )
    issues = plan_validation_issues(outer)
    assert issues[0]["type"] == expected
    assert secret not in str(issues) + plan_repair_feedback(outer) + plan_error_message(
        issues
    )
    assert "input" not in issues[0] and "ctx" not in issues[0]


def test_repair_also_reports_missing_dependency_hidden_by_field_validation():
    data = proposal_data()
    secret = "private-model-output-never-log"
    data["tasks"][0]["priority"] = secret
    data["tasks"][0]["dependencies"] = ["T9", secret]
    with pytest.raises(ValidationError) as error:
        PlanProposalVO.model_validate(data)
    outer = StructuredOutputValidationError(
        "PlanProposalVO",
        error.value,
        AIMessage(
            content=secret,
            tool_calls=[{"name": "PlanProposalVO", "args": data, "id": "plan-1"}],
        ),
    )
    feedback = plan_repair_feedback(outer)
    assert "tasks.0.priority" in feedback
    assert "tasks.0.dependencies 引用了不存在的 T9" in feedback
    assert secret not in feedback
    assert data["tasks"][0]["dependencies"] == ["T9", secret]
