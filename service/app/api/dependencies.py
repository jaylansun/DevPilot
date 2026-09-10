from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.user import User
from app.repositories.user import get_user_by_id
from app.security import InvalidAccessTokenError, decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]


def unauthorized_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: BearerCredentials,
    session: DatabaseSession,
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise unauthorized_error()

    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise unauthorized_error() from exc

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise unauthorized_error()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
