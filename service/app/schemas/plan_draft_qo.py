from pydantic import BaseModel, ConfigDict, Field

from app.schemas.plan_vo import PlanProposalVO


class DraftSubmitQO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(strict=True, ge=1)


class DraftUpdateQO(DraftSubmitQO):
    proposal: PlanProposalVO
