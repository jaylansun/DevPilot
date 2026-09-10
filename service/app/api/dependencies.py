from typing import Annotated

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.errors import ApiError
from app.models.user import User, UserRole
from app.repositories.user import get_user_by_id
from app.security import InvalidAccessTokenError, decode_access_token


bearer_scheme = HTTPBearer(
    auto_error=False,
    description="请输入登录接口返回的 JWT 访问令牌",
)
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]


def unauthorized_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="invalid_credentials",
        message="无法验证登录凭据",
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


def require_roles(*allowed_roles: UserRole):
    """创建仅允许指定用户角色访问的依赖。"""

    allowed = frozenset(allowed_roles)

    async def check_role(current_user: CurrentUser) -> User:
        if current_user.role not in allowed:
            raise ApiError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="insufficient_permissions",
                message="当前用户没有执行此操作的权限",
            )
        return current_user

    return check_role


ReviewerUser = Annotated[
    User,
    Depends(require_roles(UserRole.REVIEWER)),
]
