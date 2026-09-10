from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.task_do import TaskStatus


class TaskCreateQO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200, description="任务标题")
    description: str = Field(default="", max_length=10000, description="任务说明")
    priority: int = Field(default=3, ge=1, le=5, description="任务优先级，1 最高，5 最低")
    status: TaskStatus = Field(default=TaskStatus.TODO, description="任务状态")
    acceptance_criteria: str = Field(
        default="",
        max_length=10000,
        description="验收标准",
    )

    @field_validator("title", "description", "acceptance_criteria", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TaskUpdateQO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, description="客户端最后读取到的任务版本号")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    priority: int | None = Field(default=None, ge=1, le=5)
    status: TaskStatus | None = None
    acceptance_criteria: str | None = Field(default=None, max_length=10000)

    @field_validator("title", "description", "acceptance_criteria", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        changed_fields = self.model_fields_set - {"version"}
        if not changed_fields:
            raise ValueError("除了版本号外，至少需要提交一个待修改字段")
        if any(getattr(self, field) is None for field in changed_fields):
            raise ValueError("待修改字段不能为 null")
        return self
