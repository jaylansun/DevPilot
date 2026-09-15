from pydantic import BaseModel, ConfigDict, Field


class PlanRequestQO(BaseModel):
    """只接收规划目标；项目与用户身份由接口和登录态确定。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    goal: str = Field(min_length=1, max_length=2000, description="本次任务规划目标")
