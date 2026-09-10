import argparse
import asyncio

from app.database import AsyncSessionFactory, close_database
from app.models.user_do import UserRole
from app.repositories.user_repository import get_user_by_username


async def set_user_role(username: str, role: UserRole) -> bool:
    """修改指定用户的角色；用户不存在时返回 False。"""

    try:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                user = await get_user_by_username(session, username.strip().casefold())
                if user is None:
                    return False
                user.role = role
        return True
    finally:
        await close_database()


def main() -> None:
    parser = argparse.ArgumentParser(description="修改 DevPilot 用户角色")
    parser.add_argument("username", help="要修改的用户名")
    parser.add_argument(
        "role",
        choices=[role.value for role in UserRole],
        help="目标角色",
    )
    arguments = parser.parse_args()

    updated = asyncio.run(set_user_role(arguments.username, UserRole(arguments.role)))
    if not updated:
        parser.error(f"用户不存在：{arguments.username}")

    print(f"用户 {arguments.username} 的角色已修改为 {arguments.role}")


if __name__ == "__main__":
    main()
