from pydantic import BaseModel, ConfigDict, Field


class RagQuestionQO(BaseModel):
    """单轮问题；身份和项目权限必须由服务端检查。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        min_length=1, max_length=2000, description="关于项目文档的问题"
    )
