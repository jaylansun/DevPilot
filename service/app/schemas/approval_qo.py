from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.plan_vo import PlanProposalVO


class ConversationCreateQO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    goal: str = Field(min_length=1, max_length=2000)


class ApprovalDecisionQO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "edit_and_approve", "reject"]
    proposal: PlanProposalVO | None = None

    @model_validator(mode="after")
    def validate_edit(self) -> Self:
        if (self.action == "edit_and_approve") != (self.proposal is not None):
            raise ValueError("仅修改后批准需要提供完整方案")
        return self
