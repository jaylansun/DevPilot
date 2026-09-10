from pwdlib import PasswordHash


_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Convert a plain-text password into an Argon2 hash for storage."""

    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a plain-text password matches a stored hash."""

    return _password_hasher.verify(password, password_hash)
