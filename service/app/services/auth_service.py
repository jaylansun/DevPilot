import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_do import UserDO
from app.repositories.user_repository import get_user_by_username
from app.security import hash_password, verify_password


class UsernameAlreadyExistsError(ValueError):
    """注册时用户名已经存在。"""


async def create_user(session: AsyncSession, username: str, password: str) -> UserDO:
    password_digest = await asyncio.to_thread(hash_password, password)

    try:
        if await get_user_by_username(session, username) is not None:
            raise UsernameAlreadyExistsError("用户名已存在")

        user = UserDO(username=username, password_hash=password_digest)
        session.add(user)
        await session.flush()
    except IntegrityError as exc:
        # 数据库唯一索引用于防止并发注册产生重复用户名。
        raise UsernameAlreadyExistsError("用户名已存在") from exc

    return user


async def authenticate_user(
    session: AsyncSession,
    username: str,
    password: str,
) -> UserDO | None:
    user = await get_user_by_username(session, username)
    if user is None:
        return None

    password_matches = await asyncio.to_thread(
        verify_password,
        password,
        user.password_hash,
    )
    return user if password_matches else None
