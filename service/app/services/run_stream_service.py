"""流式任务生命周期与 HTTP 适配；事件通道通过参数交给业务。"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Literal

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.errors import ApiError
from app.services.run_events import EventPublisher, RunEventChannel

logger = logging.getLogger(__name__)
RunOperation = Callable[[EventPublisher], Awaitable[BaseModel]]
RunKind = Literal["knowledge", "planning", "workflow", "approval"]


class StreamRunner:
    """一次流式请求一个实例，负责生产任务、超时、终止事件与取消清理。"""

    def __init__(
        self,
        run: RunOperation,
        kind: RunKind,
        request_id: str,
        *,
        timeout: float = 70,
    ):
        self._run = run
        self._kind = kind
        self._channel = RunEventChannel(request_id)
        self._timeout = timeout

    async def _produce(self) -> None:
        try:
            # 服务自身仍有 65 秒预算；额外保护包括等待名额和发送事件的时间。
            async with asyncio.timeout(self._timeout):
                result = await self._run(self._channel)
                await self._channel.emit("final", kind=self._kind, result=result)
        except Exception as exc:
            if isinstance(exc, ApiError):
                status, code, message = exc.status_code, exc.code, exc.message
            elif isinstance(exc, TimeoutError):
                status, code, message = 504, "stream_timeout", "处理超时，请重试"
            else:
                logger.warning("流式处理失败；异常类型=%s", type(exc).__name__)
                status, code, message = (
                    502,
                    "stream_unavailable",
                    "处理暂时不可用，请重试",
                )
            await self._channel.emit(
                "error",
                status=status,
                error={
                    "code": code,
                    "message": message,
                    "request_id": self._channel.request_id,
                    "details": None,
                },
            )

    async def stream(self) -> AsyncIterator[str]:
        task = asyncio.create_task(self._produce())
        try:
            while True:
                event = await self._channel.receive()
                yield event.model_dump_json() + "\n"
                if event.type in ("final", "error"):
                    break
        finally:
            # StreamingResponse 断连时关闭生成器，取消传播到模型和 Graph。
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


class NDJSONResponse(StreamingResponse):
    media_type = "application/x-ndjson"


def stream_response(
    run: RunOperation, kind: RunKind, request_id: str
) -> NDJSONResponse:
    runner = StreamRunner(run, kind, request_id)
    return NDJSONResponse(
        runner.stream(),
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
