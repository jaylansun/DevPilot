from uuid import uuid4

from starlette.responses import JSONResponse


class UploadLimitMiddleware:
    """在 multipart 解析之前限制整个请求，避免超大文件先写满临时磁盘。"""

    MAX_REQUEST_BYTES = 3 * 1024 * 1024

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].rstrip("/").endswith("/documents")
        ):
            return await self.app(scope, receive, send)
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.MAX_REQUEST_BYTES:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "document_too_large",
                            "message": "文件不能超过 2 MB",
                            "request_id": scope.get("state", {}).get(
                                "request_id", str(uuid4())
                            ),
                            "details": None,
                        }
                    },
                )
                return await response(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": b"".join(chunks),
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, replay, send)
