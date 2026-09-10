from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_do import UserDO


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> UserDO | None:
    return await session.scalar(select(UserDO).where(UserDO.id == user_id))


async def get_user_by_username(session: AsyncSession, username: str) -> UserDO | None:
    return await session.scalar(select(UserDO).where(UserDO.username == username))
