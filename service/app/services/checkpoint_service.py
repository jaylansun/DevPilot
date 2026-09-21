"""生产环境使用官方 PostgreSQL Checkpointer；连接不暴露到请求或模型。"""

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url


@asynccontextmanager
async def open_checkpointer(database_url: str):
    connection_url = (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    async with AsyncPostgresSaver.from_conn_string(connection_url) as saver:
        await saver.setup()
        yield saver
