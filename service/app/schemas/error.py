from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """统一错误详情。"""

    code: str
    message: str
    request_id: str
    details: object | None = None


class ErrorResponse(BaseModel):
    """统一错误响应。"""

    error: ErrorDetail
