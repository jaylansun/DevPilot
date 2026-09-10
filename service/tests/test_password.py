from app.security import hash_password, verify_password


def test_password_hash_does_not_store_plain_text() -> None:
    password = "安全测试密码-123"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$argon2")
    assert verify_password(password, password_hash)
    assert not verify_password("错误密码", password_hash)
