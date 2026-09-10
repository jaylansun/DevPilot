import argparse
import asyncio
from getpass import getpass

from app.database import AsyncSessionFactory, close_database
from app.models.user_do import UserRole
from app.services.auth_service import UsernameAlreadyExistsError, create_user


async def create_account(username: str, password: str, role: UserRole) -> None:
    """在独立事务中创建一个预置账号。"""

    try:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                user = await create_user(session, username.strip().casefold(), password)
                user.role = role
                await session.flush()
    finally:
        await close_database()


def main() -> None:
    parser = argparse.ArgumentParser(description="创建 DevPilot 预置账号")
    parser.add_argument("username", help="登录用户名")
    parser.add_argument(
        "--role",
        choices=[role.value for role in UserRole],
        default=UserRole.MEMBER.value,
        help="账号角色，默认 member",
    )
    arguments = parser.parse_args()

    password = getpass("请输入密码：")
    if len(password) < 8 or len(password) > 128:
        parser.error("密码长度必须为 8 至 128 个字符")
    if password != getpass("请再次输入密码："):
        parser.error("两次输入的密码不一致")

    try:
        asyncio.run(
            create_account(
                arguments.username,
                password,
                UserRole(arguments.role),
            )
        )
    except UsernameAlreadyExistsError:
        parser.error(f"用户名已存在：{arguments.username}")

    print(f"账号 {arguments.username} 已创建，角色为 {arguments.role}")


if __name__ == "__main__":
    main()
