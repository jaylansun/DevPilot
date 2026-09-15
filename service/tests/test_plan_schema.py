from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.plan_qo import PlanRequestQO
from app.schemas.plan_vo import PlanProposalVO


def proposal_data():
    return {
        "summary": "完善订单功能",
        "assumptions": ["支付方式需人工确认"],
        "risks": ["需求范围仍需确认"],
        "tasks": [
            {
                "draft_id": "T1",
                "title": "实现下单校验",
                "description": "校验库存与地址",
                "priority": 2,
                "acceptance_criteria": "库存不足时返回明确错误",
                "dependencies": [],
                "source_ids": [1],
            },
            {
                "draft_id": "T2",
                "title": "补充订单测试",
                "description": "覆盖下单异常路径",
                "priority": 3,
                "acceptance_criteria": "库存不足与地址缺失用例通过",
                "dependencies": ["T1"],
                "source_ids": [],
            },
        ],
    }


def test_plan_schema_accepts_forward_dependency_and_trims():
    data = proposal_data()
    data["tasks"].reverse()
    data["tasks"][0]["title"] = "  补充订单测试  "
    result = PlanProposalVO.model_validate(data)
    assert result.tasks[0].title == "补充订单测试"
    assert result.tasks[0].dependencies == ["T1"]
    assert PlanRequestQO(goal="  下单功能  ").goal == "下单功能"


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "  "),
        ("priority", 0),
        ("priority", 6),
        ("priority", True),
        ("priority", "2"),
        ("acceptance_criteria", ""),
        ("draft_id", "T13"),
        ("dependencies", ["T1"]),
        ("dependencies", ["T9"]),
        ("dependencies", ["T2", "T2"]),
        ("source_ids", [0]),
        ("source_ids", [1, 1]),
        ("source_ids", [True]),
        ("project_id", "模型不能指定身份"),
    ],
)
def test_plan_schema_rejects_invalid_task(field, value):
    data = proposal_data()
    data["tasks"][0][field] = value
    with pytest.raises(ValidationError):
        PlanProposalVO.model_validate(data)


@pytest.mark.parametrize(
    "case",
    ["empty", "too_many", "duplicate_id", "duplicate_title", "cycle", "identity"],
)
def test_plan_schema_rejects_invalid_proposal(case):
    data = proposal_data()
    if case == "empty":
        data["tasks"] = []
    elif case == "too_many":
        data["tasks"] = [deepcopy(data["tasks"][0]) for _ in range(13)]
    elif case == "duplicate_id":
        data["tasks"][1]["draft_id"] = "T1"
    elif case == "duplicate_title":
        data["tasks"][0]["title"] = "Create   Order"
        data["tasks"][1]["title"] = " create order "
    elif case == "cycle":
        data["tasks"][0]["dependencies"] = ["T2"]
    else:
        data["user_id"] = "不允许"
    with pytest.raises(ValidationError):
        PlanProposalVO.model_validate(data)
