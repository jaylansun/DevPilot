from pwdlib import PasswordHash


_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """将明文密码转换为可安全存储的 Argon2 哈希。"""

    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """判断明文密码是否与数据库中的密码哈希匹配。"""

    return _password_hasher.verify(password, password_hash)
