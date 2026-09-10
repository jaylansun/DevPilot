from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProjectCreateQO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=120,
        description="项目名称",
    )
    description: str = Field(
        default="",
        max_length=5000,
        description="项目说明",
    )

    @field_validator("name", "description", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ProjectUpdateQO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="新的项目名称",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="新的项目说明",
    )

    @field_validator("name", "description", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("至少需要提交一个待修改字段")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("待修改字段不能为 null")
        return self
