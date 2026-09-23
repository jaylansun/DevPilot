"""准备第十四天演示数据；重复运行保留既有账号密码、项目内容和任务修改。"""

import argparse
import asyncio
import json
import sys
from getpass import getpass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionFactory, close_database
from app.errors import ApiError
from app.models.document_do import DocumentDO
from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO
from app.models.user_do import UserRole
from app.repositories.user_repository import get_user_by_username
from app.schemas.auth_qo import UsernameQO
from app.schemas.project_qo import ProjectCreateQO
from app.schemas.task_qo import TaskCreateQO
from app.services.auth_service import authenticate_user, create_user
from app.services.document_service import upload_document, validate_document

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"


async def ensure_account(session, username, password, role):
    user = await get_user_by_username(session, username)
    if user is not None:
        if user.role != role or not await authenticate_user(
            session, username, password
        ):
            raise ValueError(f"账号 {username} 已存在，但密码或角色不符；未覆盖账号")
        return user
    user = await create_user(session, username, password)
    user.role = role
    await session.flush()
    return user


async def seed_demo(
    session: AsyncSession,
    member_password: str,
    reviewer_password: str,
    *,
    member_username: str = "demo14_member",
    reviewer_username: str = "demo14_reviewer",
) -> dict:
    """调用方持有事务；任一步失败，账号、项目、任务及文档全部回滚。"""
    member_username = UsernameQO(username=member_username).username
    reviewer_username = UsernameQO(username=reviewer_username).username
    if member_username == reviewer_username:
        raise ValueError("成员和审批人必须使用不同账号")
    if any(
        not 8 <= len(value) <= 128 for value in (member_password, reviewer_password)
    ):
        raise ValueError("两个账号的密码长度都必须为 8 至 128 个字符")
    data = json.loads((DEMO_DIR / "project.json").read_text(encoding="utf-8"))
    project_data = ProjectCreateQO(name=data["name"], description=data["description"])
    member = await ensure_account(
        session, member_username, member_password, UserRole.MEMBER
    )
    await ensure_account(
        session, reviewer_username, reviewer_password, UserRole.REVIEWER
    )

    # 稳定 ID 与账号绑定：用户改名、修改任务后，再次执行不会新建原始副本。
    project_id = uuid5(NAMESPACE_URL, f"devpilot:demo:v1:{member.id}")
    project = await session.get(ProjectDO, project_id)
    if project is None:
        project = ProjectDO(
            id=project_id, owner_id=member.id, **project_data.model_dump()
        )
        session.add(project)
        await session.flush()
    tasks = []
    for sample in data["tasks"]:
        task_id = uuid5(project_id, sample["key"])
        task = await session.get(TaskDO, task_id)
        if task is None:
            task_data = TaskCreateQO.model_validate(
                {k: v for k, v in sample.items() if k != "key"}
            )
            task = TaskDO(id=task_id, project_id=project.id, **task_data.model_dump())
            session.add(task)
        tasks.append(str(task.id))
    await session.flush()

    raw = (DEMO_DIR / "restaurant.md").read_bytes()
    filename, _, digest = validate_document("restaurant.md", raw)
    document = await session.scalar(
        select(DocumentDO).where(
            DocumentDO.project_id == project.id,
            DocumentDO.content_hash == digest,
        )
    )
    if document is None:
        document = await upload_document(session, member.id, project.id, filename, raw)
    return {
        "member": member_username,
        "reviewer": reviewer_username,
        "project_id": str(project.id),
        "project_name": project.name,
        "task_ids": tasks,
        "document_id": str(document.id),
        "document_status": document.status.value,
    }


async def prepare(member_password, reviewer_password, **kwargs):
    try:
        async with AsyncSessionFactory.begin() as session:
            return await seed_demo(
                session, member_password, reviewer_password, **kwargs
            )
    finally:
        await close_database()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--member", default="demo14_member")
    parser.add_argument("--reviewer", default="demo14_reviewer")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="自动化使用：从标准输入依次读取成员和审批人密码，每行一个",
    )
    args = parser.parse_args()
    if args.password_stdin:
        member_password, reviewer_password = (
            sys.stdin.readline().rstrip("\r\n") for _ in range(2)
        )
    else:
        member_password = getpass(
            f"成员 {args.member} 的密码（已有账号请输入原密码）："
        )
        reviewer_password = getpass(
            f"审批人 {args.reviewer} 的密码（已有账号请输入原密码）："
        )
    try:
        result = asyncio.run(
            prepare(
                member_password,
                reviewer_password,
                member_username=args.member,
                reviewer_username=args.reviewer,
            )
        )
    except (ValueError, ApiError) as exc:
        parser.exit(
            1,
            f"初始化未完成：{exc.message if isinstance(exc, ApiError) else str(exc)}\n",
        )
    except IntegrityError:
        parser.exit(
            1,
            "初始化未完成：已有同名项目或任务，或另一个初始化正在执行；本次事务已回滚。\n",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        "演示数据已就绪。文档由后台索引，请在知识库等待“已就绪”；重复执行不会重置修改。"
    )


if __name__ == "__main__":
    main()
