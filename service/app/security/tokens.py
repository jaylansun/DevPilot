from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.config import get_settings


JWT_ALGORITHM = "HS256"


class InvalidAccessTokenError(ValueError):
    """Raised when an access token is malformed, altered, or expired."""


def create_access_token(user_id: UUID, expires_delta: timedelta | None = None) -> str:
    """Create a signed, time-limited JWT for one user."""

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
    """Validate an access token and return its user ID."""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            raise ValueError("unexpected token type")

        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise ValueError("missing token subject")

        return UUID(subject)
    except (jwt.InvalidTokenError, TypeError, ValueError) as exc:
        raise InvalidAccessTokenError("Invalid or expired access token") from exc
