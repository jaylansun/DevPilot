from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorkflowIntent = Literal[
    "knowledge_question", "task_lookup", "requirement_check", "clarify"
]


class WorkflowRequestQO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=2000)
    intent: Literal[
        "auto", "knowledge_question", "task_lookup", "requirement_check"
    ] = "auto"
