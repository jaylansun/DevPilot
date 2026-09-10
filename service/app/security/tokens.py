from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.config import get_settings


JWT_ALGORITHM = "HS256"


class InvalidAccessTokenError(ValueError):
    """访问令牌格式错误、被篡改或已过期时抛出。"""


def create_access_token(user_id: UUID, expires_delta: timedelta | None = None) -> str:
    """为指定用户创建带签名且具有有效期的 JWT。"""

    settings = get_settings()
    issued_at = datetime.now(UTC)
    expires_at = issued_at + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": issued_at,
        "exp": expires_at,
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> UUID:
    """验证访问令牌并返回其中的用户 ID。"""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            raise ValueError("令牌类型不正确")

        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise ValueError("令牌缺少用户标识")

        return UUID(subject)
    except (jwt.InvalidTokenError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError("访问令牌无效或已过期") from exc
