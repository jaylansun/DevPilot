from pydantic import BaseModel


class ErrorDetailVO(BaseModel):
    """统一错误详情。"""

    code: str
    message: str
    request_id: str
    details: object | None = None


class ErrorVO(BaseModel):
    """统一错误响应。"""

    error: ErrorDetailVO
