"""显式传递的执行事件：业务只依赖发送接口，队列按请求创建。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, Protocol, runtime_checkable
from uuid import uuid4

from app.schemas.stream_vo import StepName, StreamEvent, stream_event_adapter


@runtime_checkable
class EventPublisher(Protocol):
    """业务层只报告事件，不接触队列消费或 HTTP 响应。"""

    async def emit(self, event_type: str, **data: object) -> None: ...


class NullEventPublisher:
    """普通 JSON 请求忽略进度；无可变状态，可以复用。"""

    async def emit(self, event_type: str, **data: object) -> None:
        pass


NOOP_EVENTS: EventPublisher = NullEventPublisher()


class RunEventChannel:
    """一次请求一个实例；多个生产者、一个消费者，最多缓存 32 个事件。"""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self._queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=32)
        self._seq = 0

    async def emit(self, event_type: str, **data: object) -> None:
        event = stream_event_adapter.validate_python(
            {
                **data,
                "version": 1,
                "seq": 1,
                "request_id": self.request_id,
                "type": event_type,
            }
        )
        await self._queue.put(event)

    async def receive(self) -> StreamEvent:
        event = await self._queue.get()
        # 只在消费时编号，校验失败或排队时取消不会留下序号空洞。
        self._seq += 1
        event.seq = self._seq
        return event


@asynccontextmanager
async def trace(
    events: EventPublisher, name: StepName, *, kind: Literal["node", "tool"] = "node"
) -> AsyncIterator[None]:
    # 名称来自代码，不发送模型输入、工具参数/结果、异常正文或思考内容。
    step_id = str(uuid4())
    await events.emit(kind, id=step_id, name=name, status="started")
    try:
        yield
    except Exception:
        await events.emit(kind, id=step_id, name=name, status="failed")
        raise
    else:
        await events.emit(kind, id=step_id, name=name, status="completed")
