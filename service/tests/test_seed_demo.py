import pytest
from app.cli.seed_demo import seed_demo
from app.database import Base
from app.models import DocumentDO, ProjectDO, TaskDO, TaskStatus, UserDO, UserRole
from app.services.auth_service import authenticate_user, create_user
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'demo.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def counts(factory):
    async with factory() as session:
        return [
            await session.scalar(select(func.count()).select_from(model))
            for model in (UserDO, ProjectDO, TaskDO, DocumentDO)
        ]


async def test_seed_is_repeatable_and_preserves_edited_data_and_passwords(factory):
    from uuid import UUID

    async with factory.begin() as session:
        first = await seed_demo(session, "member-password", "reviewer-password")
    assert await counts(factory) == [2, 1, 2, 1]
    assert first["document_status"] == "queued"
    async with factory.begin() as session:
        project = await session.get(ProjectDO, UUID(first["project_id"]))
        project.name = "演示后修改的名称"
        task = await session.get(TaskDO, UUID(first["task_ids"][0]))
        task.title = "保留我的修改"
        task.status = TaskStatus.TODO
    async with factory.begin() as session:
        again = await seed_demo(session, "member-password", "reviewer-password")
        member = await authenticate_user(session, "demo14_member", "member-password")
        reviewer = await authenticate_user(
            session, "demo14_reviewer", "reviewer-password"
        )
        assert member.role == UserRole.MEMBER
        assert reviewer.role == UserRole.REVIEWER
        task = await session.get(TaskDO, UUID(first["task_ids"][0]))
        assert (task.title, task.status) == ("保留我的修改", TaskStatus.TODO)
    assert again["project_name"] == "演示后修改的名称"
    assert again["task_ids"] == first["task_ids"]
    assert again["document_id"] == first["document_id"]
    assert await counts(factory) == [2, 1, 2, 1]


@pytest.mark.parametrize("conflict", ["password", "role"])
async def test_existing_reviewer_conflict_rolls_back_new_member(factory, conflict):
    async with factory.begin() as session:
        reviewer = await create_user(session, "demo14_reviewer", "reviewer-password")
        reviewer.role = UserRole.REVIEWER if conflict == "password" else UserRole.MEMBER
    with pytest.raises(ValueError, match="密码或角色不符"):
        async with factory.begin() as session:
            await seed_demo(
                session,
                "member-password",
                "wrong-password" if conflict == "password" else "reviewer-password",
            )
    assert await counts(factory) == [1, 0, 0, 0]
    async with factory() as session:
        assert await authenticate_user(session, "demo14_reviewer", "reviewer-password")


async def test_same_username_and_short_password_do_not_write(factory):
    for kwargs, password in [
        ({"reviewer_username": "demo14_member"}, "valid-password"),
        ({}, "short"),
    ]:
        with pytest.raises(ValueError):
            async with factory.begin() as session:
                await seed_demo(session, password, "reviewer-password", **kwargs)
    assert await counts(factory) == [0, 0, 0, 0]
