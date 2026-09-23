from typing import Annotated

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db_session, get_session_factory
from app.errors import ApiError
from app.models.user_do import UserDO, UserRole
from app.repositories.user_repository import get_user_by_id
from app.security import InvalidAccessTokenError, decode_access_token

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="请输入登录接口返回的 JWT 访问令牌",
)
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
SessionFactory = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_session_factory)
]
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
    sessions: SessionFactory,
) -> UserDO:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise unauthorized_error()

    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidAccessTokenError as exc:
        raise unauthorized_error() from exc

    # 鉴权查询在此结束，不占用整个路由执行或流式响应的数据库连接。
    async with sessions() as session:
        user = await get_user_by_id(session, user_id)
    if user is None:
        raise unauthorized_error()

    return user


CurrentUser = Annotated[UserDO, Depends(get_current_user)]


def require_roles(*allowed_roles: UserRole):
    """创建仅允许指定用户角色访问的依赖。"""

    allowed = frozenset(allowed_roles)

    async def check_role(current_user: CurrentUser) -> UserDO:
        if current_user.role not in allowed:
            raise ApiError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="insufficient_permissions",
                message="当前用户没有执行此操作的权限",
            )
        return current_user

    return check_role


ReviewerUser = Annotated[
    UserDO,
    Depends(require_roles(UserRole.REVIEWER)),
]

MemberUser = Annotated[
    UserDO,
    Depends(require_roles(UserRole.MEMBER)),
]
