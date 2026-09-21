"""一次规划一个稳定 thread；审批决定先落库，任务与执行结果在同一事务提交。"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid5
from weakref import WeakValueDictionary

from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.models.approval_do import ApprovalDO, ConversationDO
from app.models.document_do import DocumentDO, DocumentStatus
from app.models.project_do import ProjectDO
from app.models.task_do import TaskDO, TaskSource, TaskStatus
from app.models.user_do import UserDO, UserRole
from app.schemas.approval_qo import ApprovalDecisionQO
from app.schemas.approval_vo import ApprovalPageVO, ApprovalVO, ConversationVO
from app.schemas.plan_vo import PlanProposalVO, PlanResultVO, normalize_task_title
from app.services.approval_graph import ApprovalContext, ApprovalGraph
from app.services.document_service import require_document_project
from app.services.run_events import NOOP_EVENTS, EventPublisher


class ApprovalService:
    def __init__(self, session_factory, planner, checkpointer):
        self.sessions = session_factory
        self.planner = planner
        self.graph = ApprovalGraph(self, checkpointer).graph
        # 当前部署为单 API 实例；同一 thread 的执行串行化，空闲锁自动释放。
        self._locks: WeakValueDictionary[UUID, asyncio.Lock] = WeakValueDictionary()

    @asynccontextmanager
    async def execution_lock(self, conversation_id: UUID):
        lock = self._locks.setdefault(conversation_id, asyncio.Lock())
        try:
            await asyncio.wait_for(lock.acquire(), timeout=1)
        except TimeoutError as exc:
            raise ApiError(
                409, "approval_busy", "该流程正在执行，请稍后刷新或重试"
            ) from exc
        try:
            yield
        finally:
            lock.release()

    @staticmethod
    def config(conversation: ConversationDO) -> dict:
        return {
            "configurable": {"thread_id": conversation.thread_id},
            "recursion_limit": 12,
        }

    async def require_conversation(self, session, conversation_id, user):
        conversation = await session.get(ConversationDO, conversation_id)
        if conversation is None:
            raise ApiError(404, "conversation_not_found", "规划会话不存在")
        if user.role == UserRole.MEMBER:
            await require_document_project(session, user.id, conversation.project_id)
            if conversation.owner_id != user.id:
                raise ApiError(404, "conversation_not_found", "规划会话不存在")
        elif user.role == UserRole.REVIEWER:
            # 审批人只能查看已提交的方案，不能读取成员的未提交会话。
            if await session.get(ApprovalDO, conversation.id) is None:
                raise ApiError(404, "approval_not_found", "审批记录不存在")
        else:
            raise ApiError(403, "insufficient_permissions", "没有操作权限")
        return conversation

    async def create(self, user, project_id, goal) -> ConversationVO:
        if user.role != UserRole.MEMBER:
            raise ApiError(403, "insufficient_permissions", "仅成员可以创建规划")
        async with self.sessions.begin() as session:
            await require_document_project(session, user.id, project_id)
            conversation = ConversationDO(
                project_id=project_id, owner_id=user.id, goal=goal
            )
            session.add(conversation)
            await session.flush()
            return ConversationVO(
                id=conversation.id,
                project_id=project_id,
                goal=goal,
                status="new",
                approval=None,
            )

    async def approval_view(self, session, approval: ApprovalDO) -> ApprovalVO:
        conversation = await session.get(ConversationDO, approval.conversation_id)
        project = await session.get(ProjectDO, conversation.project_id)
        return ApprovalVO(
            id=approval.id,
            conversation_id=conversation.id,
            project_id=project.id,
            project_name=project.name,
            goal=conversation.goal,
            status=approval.status,
            plan=approval.plan,
            decision=approval.decision,
            reviewer_id=approval.reviewer_id,
            created_tasks=approval.created_tasks,
            created_at=approval.created_at,
            decided_at=approval.decided_at,
        )

    async def get(self, user, conversation_id) -> ConversationVO:
        async with self.sessions() as session:
            conversation = await self.require_conversation(
                session, conversation_id, user
            )
            approval = await session.get(ApprovalDO, conversation_id)
            snapshot = await self.graph.aget_state(self.config(conversation))
            return ConversationVO(
                id=conversation.id,
                project_id=conversation.project_id,
                goal=conversation.goal,
                status=approval.status
                if approval
                else "interrupted"
                if snapshot.values
                else "new",
                approval=await self.approval_view(session, approval)
                if approval
                else None,
            )

    async def conversations(self, user, project_id, offset=0, limit=20):
        async with self.sessions() as session:
            await require_document_project(session, user.id, project_id)
            ids = list(
                await session.scalars(
                    select(ConversationDO.id)
                    .where(
                        ConversationDO.project_id == project_id,
                        ConversationDO.owner_id == user.id,
                    )
                    .order_by(ConversationDO.created_at.desc(), ConversationDO.id)
                    .offset(offset)
                    .limit(limit)
                )
            )
        return [await self.get(user, id) for id in ids]

    async def get_approval(self, user, approval_id) -> ApprovalVO:
        async with self.sessions() as session:
            approval = await session.get(ApprovalDO, approval_id)
            if approval is None:
                raise ApiError(404, "approval_not_found", "审批记录不存在")
            await self.require_conversation(session, approval.conversation_id, user)
            return await self.approval_view(session, approval)

    async def list_approvals(self, user, status, offset, limit) -> ApprovalPageVO:
        async with self.sessions() as session:
            statement = select(ApprovalDO).join(ConversationDO)
            if user.role == UserRole.MEMBER:
                statement = statement.where(ConversationDO.owner_id == user.id)
            if status:
                statement = statement.where(ApprovalDO.status == status)
            total = await session.scalar(
                select(func.count()).select_from(statement.subquery())
            )
            approvals = list(
                await session.scalars(
                    statement.order_by(ApprovalDO.created_at.desc(), ApprovalDO.id)
                    .offset(offset)
                    .limit(limit)
                )
            )
            return ApprovalPageVO(
                items=[await self.approval_view(session, a) for a in approvals],
                total=total,
                offset=offset,
                limit=limit,
            )

    async def generate(self, context: ApprovalContext, goal: str):
        async with self.sessions() as session:
            return await self.planner.create(
                session,
                context.owner_id,
                context.project_id,
                goal,
                events=context.events,
            )

    async def document_hashes(self, session, project_id, plan):
        ids = {source.document_id for source in plan.sources}
        documents = list(
            await session.scalars(
                select(DocumentDO)
                .where(
                    DocumentDO.project_id == project_id,
                    DocumentDO.id.in_(ids),
                    DocumentDO.status == DocumentStatus.READY,
                )
                .with_for_update()
            )
        )
        if not ids or len(documents) != len(ids):
            raise ApiError(
                409, "approval_documents_changed", "方案引用的资料已变化，请重新规划"
            )
        return {str(doc.id): doc.content_hash for doc in documents}

    async def record_submission(self, context: ApprovalContext, data: dict):
        plan = PlanResultVO.model_validate(data)
        async with self.sessions.begin() as session:
            await require_document_project(
                session, context.owner_id, context.project_id
            )
            existing = await session.get(ApprovalDO, context.conversation_id)
            if existing:
                return existing
            hashes = await self.document_hashes(session, context.project_id, plan)
            approval = ApprovalDO(
                id=context.conversation_id,
                conversation_id=context.conversation_id,
                plan=plan.model_dump(mode="json"),
                document_hashes=hashes,
            )
            session.add(approval)
            await session.flush()
            return approval

    async def start(
        self, user, conversation_id, *, events: EventPublisher = NOOP_EVENTS
    ) -> ApprovalVO:
        if user.role != UserRole.MEMBER:
            raise ApiError(403, "insufficient_permissions", "仅成员可以提交规划")
        async with self.execution_lock(conversation_id):
            async with self.sessions() as session:
                conversation = await self.require_conversation(
                    session, conversation_id, user
                )
                existing = await session.get(ApprovalDO, conversation_id)
                if existing and existing.status != "pending":
                    return await self.approval_view(session, existing)
            config = self.config(conversation)
            snapshot = await self.graph.aget_state(config)
            # 请求中断后用同一 thread 继续，不重复生成已保存的方案。
            if not any(task.interrupts for task in snapshot.tasks):
                await self.graph.ainvoke(
                    None if snapshot.values else {"goal": conversation.goal},
                    config=config,
                    durability="sync",
                    context=ApprovalContext(
                        conversation.id, user.id, conversation.project_id, events
                    ),
                )
            result = await self.get_approval(user, conversation_id)
            await events.emit("approval_required", approval=result)
            return result

    async def validate_decision(self, session, conversation, approval, decision):
        if decision.action == "reject":
            return None
        plan = PlanResultVO.model_validate(approval.plan)
        proposal = decision.proposal or plan.proposal
        available = {source.source_id for source in plan.sources}
        referenced = {id for task in proposal.tasks for id in task.source_ids}
        if not referenced or not referenced <= available:
            raise ApiError(
                422, "invalid_approval_sources", "修改后的任务引用了无效资料"
            )
        hashes = await self.document_hashes(session, conversation.project_id, plan)
        if hashes != approval.document_hashes:
            raise ApiError(
                409, "approval_documents_changed", "资料内容已变化，请重新规划"
            )
        # 锁定项目，串行化多个审批向同一项目写入任务。
        await session.scalar(
            select(ProjectDO)
            .where(ProjectDO.id == conversation.project_id)
            .with_for_update()
        )
        titles = await session.scalars(
            select(TaskDO.title).where(TaskDO.project_id == conversation.project_id)
        )
        existing = {normalize_task_title(title) for title in titles}
        if any(normalize_task_title(task.title) in existing for task in proposal.tasks):
            raise ApiError(
                409, "approval_task_conflict", "看板已有同名任务，请修改方案后批准"
            )
        return PlanProposalVO.model_validate(proposal.model_dump())

    async def decide(
        self,
        user,
        approval_id,
        body: ApprovalDecisionQO,
        *,
        events: EventPublisher = NOOP_EVENTS,
    ) -> ApprovalVO:
        if user.role != UserRole.REVIEWER:
            raise ApiError(403, "insufficient_permissions", "仅审批人可以作出决定")
        data = body.model_dump(mode="json")
        async with self.execution_lock(approval_id):
            async with self.sessions.begin() as session:
                approval = await session.get(
                    ApprovalDO, approval_id, with_for_update=True
                )
                if approval is None:
                    raise ApiError(404, "approval_not_found", "审批记录不存在")
                conversation = await self.require_conversation(
                    session, approval.conversation_id, user
                )
                if approval.decision is not None:
                    if approval.decision != data or approval.reviewer_id != user.id:
                        raise ApiError(
                            409,
                            "approval_already_decided",
                            "已记录审批决定，请刷新；重试必须使用原决定",
                        )
                    if approval.status in ("approved", "rejected"):
                        return await self.approval_view(session, approval)
                config = self.config(conversation)
                snapshot = await self.graph.aget_state(config)
                if not snapshot.values:
                    raise ApiError(
                        409,
                        "approval_checkpoint_missing",
                        "流程状态缺失，请联系维护者恢复检查点",
                    )
                if approval.decision is None:
                    await self.validate_decision(session, conversation, approval, body)
                    approval.decision = data
                    approval.reviewer_id = user.id
                    approval.decided_at = datetime.now(UTC)
                    approval.status = "processing"
            # 决定已提交；即使 HTTP 断开，也可由同一审批人用同一决定恢复。
            context = ApprovalContext(
                conversation.id,
                conversation.owner_id,
                conversation.project_id,
                events,
                user.id,
            )
            # 方案写库后、interrupt 前断开时，先完成暂停点，再应用已保存的决定。
            # 这些节点只复用已经生成的方案，不会重新调用模型。
            if set(snapshot.next) & {"submit_approval", "await_approval"} and not any(
                task.interrupts for task in snapshot.tasks
            ):
                await self.graph.ainvoke(
                    None, config=config, durability="sync", context=context
                )
                snapshot = await self.graph.aget_state(config)
            resume = (
                Command(resume=data)
                if any(t.interrupts for t in snapshot.tasks)
                else None
            )
            await self.graph.ainvoke(
                resume,
                config=config,
                durability="sync",
                context=context,
            )
            return await self.get_approval(user, approval_id)

    async def persist_decision(
        self, context: ApprovalContext, data: dict
    ) -> ApprovalVO:
        body = ApprovalDecisionQO.model_validate(data)
        try:
            async with self.sessions.begin() as session:
                approval = await session.get(
                    ApprovalDO, context.conversation_id, with_for_update=True
                )
                reviewer = (
                    await session.get(UserDO, context.reviewer_id)
                    if context.reviewer_id
                    else None
                )
                if (
                    approval is None
                    or reviewer is None
                    or reviewer.role != UserRole.REVIEWER
                    or approval.reviewer_id != reviewer.id
                    or approval.decision != data
                ):
                    raise ApiError(
                        403, "approval_not_authorized", "没有有效的人工审批决定"
                    )
                if approval.status in ("approved", "rejected"):
                    return await self.approval_view(session, approval)
                conversation = await session.get(
                    ConversationDO, approval.conversation_id
                )
                proposal = await self.validate_decision(
                    session, conversation, approval, body
                )
                created = []
                if proposal:
                    ids = {
                        task.draft_id: uuid5(approval.execution_key, task.draft_id)
                        for task in proposal.tasks
                    }
                    for draft in proposal.tasks:
                        dependencies = [str(ids[id]) for id in draft.dependencies]
                        session.add(
                            TaskDO(
                                id=ids[draft.draft_id],
                                project_id=conversation.project_id,
                                title=draft.title,
                                description=draft.description,
                                priority=draft.priority,
                                acceptance_criteria=draft.acceptance_criteria,
                                source=TaskSource.AI,
                                status=TaskStatus.TODO,
                                approval_id=approval.id,
                                draft_id=draft.draft_id,
                                dependency_ids=dependencies,
                            )
                        )
                        created.append(
                            {
                                "draft_id": draft.draft_id,
                                "task_id": str(ids[draft.draft_id]),
                                "title": draft.title,
                                "dependency_ids": dependencies,
                            }
                        )
                approval.created_tasks = created
                approval.status = "approved" if proposal else "rejected"
                await session.flush()
                result = await self.approval_view(session, approval)
            # 返回前确保任务和审批执行结果都已提交。
            return result
        except IntegrityError as exc:
            raise ApiError(
                409,
                "approval_task_conflict",
                "任务写入发生冲突，未部分写入；请刷新看板核对后重试",
            ) from exc
