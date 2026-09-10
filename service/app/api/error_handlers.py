import logging
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.errors import ApiError


logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
    details: object | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": _request_id(request),
                "details": details,
            }
        },
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        headers=exc.headers,
        details=exc.details,
    )


async def http_error_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    default_codes = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
    }
    default_messages = {
        400: "请求内容不正确",
        401: "用户尚未登录或登录已失效",
        403: "当前用户没有访问权限",
        404: "请求的资源不存在",
        405: "该接口不支持当前请求方法",
        409: "请求与当前数据状态冲突",
    }
    return _error_response(
        request,
        status_code=exc.status_code,
        code=default_codes.get(exc.status_code, "http_error"),
        message=default_messages.get(exc.status_code, "请求处理失败"),
        headers=dict(exc.headers or {}),
    )


def _validation_message(error: dict[str, object]) -> str:
    error_type = str(error.get("type", ""))
    context = error.get("ctx")
    values = context if isinstance(context, dict) else {}

    messages = {
        "missing": "字段不能为空",
        "string_type": "必须是字符串",
        "string_pattern_mismatch": "字符串格式不正确",
        "int_type": "必须是整数",
        "int_parsing": "必须是有效的整数",
        "bool_type": "必须是布尔值",
        "bool_parsing": "必须是有效的布尔值",
        "uuid_type": "必须是 UUID",
        "uuid_parsing": "必须是有效的 UUID",
        "json_invalid": "JSON 格式不正确",
        "extra_forbidden": "不允许提交该字段",
    }
    if error_type == "string_too_short":
        return f"字符串长度不能少于 {values.get('min_length')} 个字符"
    if error_type == "string_too_long":
        return f"字符串长度不能超过 {values.get('max_length')} 个字符"
    if error_type == "greater_than":
        return f"数值必须大于 {values.get('gt')}"
    if error_type == "greater_than_equal":
        return f"数值不能小于 {values.get('ge')}"
    if error_type == "less_than":
        return f"数值必须小于 {values.get('lt')}"
    if error_type == "less_than_equal":
        return f"数值不能大于 {values.get('le')}"
    return messages.get(error_type, "输入内容不符合要求")


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": _validation_message(error),
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status_code=422,
        code="validation_error",
        message="请求参数校验失败",
        details=details,
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception("未处理的接口异常；请求 ID=%s", request_id, exc_info=exc)
    return _error_response(
        request,
        status_code=500,
        code="internal_error",
        message="服务器发生意外错误",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
