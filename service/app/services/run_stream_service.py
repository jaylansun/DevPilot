"""请求级事件通道：有界队列背压、断开取消、只发送显式允许的执行信息。"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from uuid import uuid4

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.errors import ApiError
from app.schemas.stream_vo import StepName, stream_event_adapter

logger = logging.getLogger(__name__)
_sink: ContextVar[Callable[..., Awaitable[None]] | None] = ContextVar(
    "run_event_sink", default=None
)


def is_streaming() -> bool:
    return _sink.get() is not None


async def emit(event_type: str, **data) -> None:
    sink = _sink.get()
    if sink is not None:
        await sink(event_type, **data)


@asynccontextmanager
async def trace(name: StepName, *, kind: str = "node"):
    # 名称来自代码，不发送模型输入、工具参数/结果、异常正文或思考内容。
    step_id = str(uuid4())
    await emit(kind, id=step_id, name=name, status="started")
    try:
        yield
    except Exception:
        await emit(kind, id=step_id, name=name, status="failed")
        raise
    else:
        await emit(kind, id=step_id, name=name, status="completed")


async def stream_events(
    run: Callable[[], Awaitable[BaseModel]], kind: str, request_id: str
):
    queue: asyncio.Queue = asyncio.Queue(maxsize=32)
    seq = 0

    async def send(event_type: str, **data):
        event = stream_event_adapter.validate_python(
            {
                "version": 1,
                "seq": 1,
                "request_id": request_id,
                "type": event_type,
                **data,
            }
        )
        await queue.put(event)

    async def produce():
        token = _sink.set(send)
        try:
            # 服务自身仍有 65 秒预算；额外保护包括等待名额和发送事件的时间。
            async with asyncio.timeout(70):
                result = await run()
                await send("final", kind=kind, result=result)
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
            await send(
                "error",
                status=status,
                error={
                    "code": code,
                    "message": message,
                    "request_id": request_id,
                    "details": None,
                },
            )
        finally:
            _sink.reset(token)

    task = asyncio.create_task(produce())
    try:
        while True:
            event = await queue.get()
            # 在唯一消费者中编号，校验失败或排队期间取消不会留下序号空洞。
            seq += 1
            event.seq = seq
            yield event.model_dump_json() + "\n"
            if event.type in ("final", "error"):
                break
    finally:
        # StreamingResponse 收到断连会关闭生成器，向模型和 Graph 传递取消。
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


class NDJSONResponse(StreamingResponse):
    media_type = "application/x-ndjson"


def stream_response(
    run: Callable[[], Awaitable[BaseModel]], kind: str, request_id: str
):
    return NDJSONResponse(
        stream_events(run, kind, request_id),
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
