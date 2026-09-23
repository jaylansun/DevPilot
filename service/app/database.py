from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """所有 SQLAlchemy 数据模型共用的基类。"""


settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """普通接口事务；必须通过 function scope 在响应发送前完成提交。"""

    async with AsyncSessionFactory() as session:
        try:
            async with session.begin():
                yield session
        except Exception:
            await session.rollback()
            raise


def get_session_factory():
    """短会话由调用者持有，不能跨模型调用或流式发送共享。"""
    return AsyncSessionFactory


async def close_database() -> None:
    """应用关闭时释放连接池中的全部数据库连接。"""

    await engine.dispose()
