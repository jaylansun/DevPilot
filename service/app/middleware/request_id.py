from collections.abc import Awaitable, Callable
import re
from uuid import uuid4

from starlette.requests import Request
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    provided_request_id = request.headers.get(REQUEST_ID_HEADER, "")
    request_id = (
        provided_request_id
        if _VALID_REQUEST_ID.fullmatch(provided_request_id)
        else str(uuid4())
    )
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
