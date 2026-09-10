from datetime import timedelta
from uuid import uuid4

import pytest

from app.security import InvalidAccessTokenError, create_access_token, decode_access_token


def test_access_token_contains_user_id() -> None:
    user_id = uuid4()

    token = create_access_token(user_id)

    assert decode_access_token(token) == user_id


def test_tampered_access_token_is_rejected() -> None:
    token = create_access_token(uuid4())
    header, payload, signature = token.split(".")
    changed_signature = ("a" if signature[0] != "a" else "b") + signature[1:]

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(".".join((header, payload, changed_signature)))


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token(uuid4(), expires_delta=timedelta(seconds=-1))

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)
