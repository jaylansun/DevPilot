import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import get_user_by_username
from app.security import hash_password, verify_password


class UsernameAlreadyExistsError(ValueError):
    """Raised when registration uses an existing username."""


async def register_user(session: AsyncSession, username: str, password: str) -> User:
    password_digest = await asyncio.to_thread(hash_password, password)

    try:
        async with session.begin():
            if await get_user_by_username(session, username) is not None:
                raise UsernameAlreadyExistsError("Username already exists")

            user = User(username=username, password_hash=password_digest)
            session.add(user)
            await session.flush()
    except IntegrityError as exc:
        # The database unique index protects against simultaneous registrations.
        raise UsernameAlreadyExistsError("Username already exists") from exc

    return user


async def authenticate_user(
    session: AsyncSession,
    username: str,
    password: str,
) -> User | None:
    user = await get_user_by_username(session, username)
    if user is None:
        return None

    password_matches = await asyncio.to_thread(
        verify_password,
        password,
        user.password_hash,
    )
    return user if password_matches else None
