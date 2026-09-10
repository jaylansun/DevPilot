from datetime import datetime

from pydantic import BaseModel


class HealthVO(BaseModel):
    """服务健康检查结果。"""

    status: str
    service: str
    timestamp: datetime
    ai_mode: str
