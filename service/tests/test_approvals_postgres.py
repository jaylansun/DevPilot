"""使用独立 PostgreSQL 测试库验证迁移、真实 Checkpoint 和事务；不连接默认数据库。"""

import os
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO
from app.models.user_do import UserDO, UserRole
from app.schemas.approval_qo import ApprovalDecisionQO
from app.services.approval_service import ApprovalService
from app.services.checkpoint_service import open_checkpointer
from app.services.document_index_service import RetrievedChunk
from app.services.plan_agent_service import PlanAgentService
from app.services.plan_service import PlanService
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_rag_model import configuration


@pytest.mark.skipif(
    not os.getenv("TEST_APPROVAL_DATABASE_URL"), reason="需要独立 PostgreSQL 测试库"
)
async def test_postgres_restart_transaction_rollback_and_idempotent_recovery():
    url = os.environ["TEST_APPROVAL_DATABASE_URL"]
    engine = create_async_engine(url)
    assert engine.url.database in {"day12_test", "day13_test"}, (
        "仅允许使用明确命名的隔离测试库"
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    member = UserDO(
        id=uuid4(), username=str(uuid4()), password_hash="test", role=UserRole.MEMBER
    )
    reviewer = UserDO(
        id=uuid4(), username=str(uuid4()), password_hash="test", role=UserRole.REVIEWER
    )
    project_id, document_id = uuid4(), uuid4()
    try:
        async with factory.begin() as session:
            session.add_all([member, reviewer])
            await session.flush()
            session.add(ProjectDO(id=project_id, owner_id=member.id, name="审批验证"))
            await session.flush()
            session.add(
                DocumentDO(
                    id=document_id,
                    project_id=project_id,
                    filename="规则.md",
                    content="订单不得重复提交",
                    content_hash="a" * 64,
                    size_bytes=30,
                    status=DocumentStatus.READY,
                    chunk_count=1,
                )
            )
        index = Mock()
        index.search.return_value = [
            RetrievedChunk(document_id, 0, "订单不得重复提交", "订单", 0.9)
        ]
        settings = configuration()
        planner = PlanService(settings, index, factory, PlanAgentService(settings))
        async with open_checkpointer(url) as saver:
            service = ApprovalService(factory, planner, saver)
            conversation = await service.create(member, project_id, "实现订单功能")
            approval = await service.start(member, conversation.id)
            assert approval.status == "pending"
        async with open_checkpointer(url) as saver:
            service = ApprovalService(factory, planner, saver)
            planner.create = AsyncMock(
                side_effect=AssertionError("重启恢复不能重新生成方案")
            )
            assert (await service.get(member, conversation.id)).status == "pending"

            def fail_after_insert(_conn, _cursor, statement, *_):
                if statement.startswith("INSERT INTO tasks"):
                    raise RuntimeError("模拟任务已插入但事务尚未提交时崩溃")

            event.listen(engine.sync_engine, "after_cursor_execute", fail_after_insert)
            try:
                with pytest.raises(RuntimeError):
                    await service.decide(
                        reviewer, approval.id, ApprovalDecisionQO(action="approve")
                    )
            finally:
                event.remove(
                    engine.sync_engine, "after_cursor_execute", fail_after_insert
                )
            async with factory() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(TaskDO)
                        .where(TaskDO.project_id == project_id)
                    )
                    == 0
                )
            first = await service.decide(
                reviewer, approval.id, ApprovalDecisionQO(action="approve")
            )
            second = await service.decide(
                reviewer, approval.id, ApprovalDecisionQO(action="approve")
            )
            assert (
                first.status == "approved"
                and first.created_tasks == second.created_tasks
            )
            async with factory() as session:
                assert await session.scalar(
                    select(func.count())
                    .select_from(TaskDO)
                    .where(TaskDO.project_id == project_id)
                ) == len(first.created_tasks)
    finally:
        await engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_APPROVAL_DATABASE_URL"), reason="需要独立 PostgreSQL 测试库"
)
async def test_postgres_draft_versions_concurrent_submit_and_restart():
    import asyncio

    from app.errors import ApiError
    from app.models.approval_do import ConversationDO
    from app.schemas.plan_draft_qo import DraftSubmitQO, DraftUpdateQO
    from app.services.plan_draft_service import PlanDraftService

    url = os.environ["TEST_APPROVAL_DATABASE_URL"]
    engine = create_async_engine(url)
    assert engine.url.database in {"day12_test", "day13_test"}
    factory = async_sessionmaker(engine, expire_on_commit=False)
    member = UserDO(
        id=uuid4(), username=str(uuid4()), password_hash="test", role=UserRole.MEMBER
    )
    project_id, document_id = uuid4(), uuid4()
    try:
        async with factory.begin() as session:
            session.add(member)
            await session.flush()
            session.add(
                ProjectDO(id=project_id, owner_id=member.id, name="草案并发验证")
            )
            await session.flush()
            session.add(
                DocumentDO(
                    id=document_id,
                    project_id=project_id,
                    filename="规则.md",
                    content="订单不得重复提交",
                    content_hash="b" * 64,
                    size_bytes=30,
                    status=DocumentStatus.READY,
                    chunk_count=1,
                )
            )
        index = Mock()
        index.search.return_value = [
            RetrievedChunk(document_id, 0, "订单不得重复提交", "订单", 0.9)
        ]
        settings = configuration()
        planner = PlanService(settings, index, factory, PlanAgentService(settings))
        async with open_checkpointer(url) as saver:
            approvals = ApprovalService(factory, planner, saver)
            drafts = PlanDraftService(factory, planner, approvals)
            draft = await drafts.generate(member, project_id, "完善订单校验")
            planner.create = AsyncMock(side_effect=AssertionError("送审不能重新生成"))
            # 两个独立事务修改同一版本，必须只有一个成功，另一个返回 409。
            proposal = draft.plan.proposal.model_copy(deep=True)
            proposal.tasks[0].title = "成员确认的任务"
            results = await asyncio.gather(
                *(
                    drafts.update(
                        member,
                        project_id,
                        draft.id,
                        DraftUpdateQO(version=1, proposal=proposal),
                    )
                    for _ in range(2)
                ),
                return_exceptions=True,
            )
            errors = [item for item in results if isinstance(item, ApiError)]
            assert len(errors) == 1 and errors[0].code == "draft_version_conflict"
            saved = await drafts.get(member, project_id, draft.id)
            assert saved.version == 2 and saved.plan.proposal == proposal
            first, second = await asyncio.gather(
                *(
                    drafts.submit(
                        member, project_id, draft.id, DraftSubmitQO(version=2)
                    )
                    for _ in range(2)
                )
            )
            assert first.id == second.id and first.plan == saved.plan
            planner.create.assert_not_awaited()
        # 新建服务和 PostgreSQL 检查点连接，恢复仍是同一版、同一会话。
        async with open_checkpointer(url) as saver:
            approvals = ApprovalService(factory, planner, saver)
            drafts = PlanDraftService(factory, planner, approvals)
            again = await drafts.submit(
                member, project_id, draft.id, DraftSubmitQO(version=2)
            )
            assert again.id == first.id and again.plan == saved.plan
            async with factory() as session:
                assert (
                    await session.scalar(
                        select(func.count(ConversationDO.id)).where(
                            ConversationDO.project_id == project_id
                        )
                    )
                    == 1
                )
            planner.create.assert_not_awaited()
    finally:
        await engine.dispose()
