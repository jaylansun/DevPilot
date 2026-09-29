from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessageQO(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequestQO(BaseModel):
    """历史仅作不可信对话上下文；身份、项目和工具结果由服务端提供。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessageQO] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_history(self) -> Self:
        if len(self.history) % 2 or any(
            message.role != ("user" if index % 2 == 0 else "assistant")
            for index, message in enumerate(self.history)
        ):
            raise ValueError("历史须为按时间排列的完整用户、助手消息对")
        if sum(len(message.content) for message in self.history) > 20000:
            raise ValueError("历史内容总长度不能超过 20000 个字符")
        return self
