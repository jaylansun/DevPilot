"""草案以服务端内容为准；编辑检查版本，送审复用保存结果，不再次调用模型。"""

from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError

from app.errors import ApiError
from app.models.approval_do import ConversationDO
from app.models.plan_draft_do import PlanDraftDO
from app.models.task_do import TaskDO
from app.models.user_do import UserRole
from app.repositories.project_repository import get_owned_project
from app.schemas.plan_draft_qo import DraftSubmitQO, DraftUpdateQO
from app.schemas.plan_draft_vo import PlanDraftPageVO, PlanDraftVO
from app.schemas.plan_vo import PlanResultVO, normalize_task_title
from app.services.document_service import require_document_project
from app.services.run_events import NOOP_EVENTS, EventPublisher


class PlanDraftService:
    def __init__(self, session_factory, planner, approvals):
        self.sessions = session_factory
        self.planner = planner
        self.approvals = approvals

    @staticmethod
    def require_member(user):
        if user.role != UserRole.MEMBER:
            raise ApiError(403, "insufficient_permissions", "仅成员可以管理规划草案")

    @staticmethod
    def view(draft):
        return PlanDraftVO(
            id=draft.id,
            project_id=draft.project_id,
            goal=draft.goal,
            plan=draft.plan,
            version=draft.version,
            status="submitted" if draft.conversation_id else "draft",
            conversation_id=draft.conversation_id,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )

    async def require_draft(self, session, user, project_id, draft_id, *, lock=False):
        self.require_member(user)
        await require_document_project(session, user.id, project_id)
        statement = select(PlanDraftDO).where(
            PlanDraftDO.id == draft_id,
            PlanDraftDO.project_id == project_id,
            PlanDraftDO.owner_id == user.id,
        )
        if lock:
            statement = statement.with_for_update()
        draft = await session.scalar(statement)
        if draft is None:
            raise ApiError(404, "draft_not_found", "规划草案不存在")
        return draft

    @staticmethod
    def check_version(draft, version):
        if draft.version != version:
            raise ApiError(
                409, "draft_version_conflict", "草案已被修改，请载入最新草案后核对"
            )

    @staticmethod
    def check_sources(plan, proposal):
        available = {source.source_id for source in plan.sources}
        referenced = {id for task in proposal.tasks for id in task.source_ids}
        if not referenced or not referenced <= available:
            raise ApiError(
                422, "invalid_draft_sources", "草案引用必须来自本次保存的资料"
            )

    async def lock_project(self, session, user, project_id):
        if await get_owned_project(session, project_id, user.id, lock=True) is None:
            raise ApiError(404, "project_not_found", "项目不存在")

    async def generate(
        self, user, project_id, goal, *, events: EventPublisher = NOOP_EVENTS
    ):
        self.require_member(user)
        plan = await self.planner.create(user.id, project_id, goal, events=events)
        plan = PlanResultVO.model_validate(plan.model_dump())
        self.check_sources(plan, plan.proposal)
        async with self.sessions.begin() as session:
            await self.lock_project(session, user, project_id)
            hashes = await self.approvals.document_hashes(session, project_id, plan)
            draft = PlanDraftDO(
                project_id=project_id,
                owner_id=user.id,
                goal=goal,
                plan={**plan.model_dump(mode="json"), "persisted": True},
                document_hashes=hashes,
            )
            session.add(draft)
            await session.flush()
            result = self.view(draft)
        # 只有事务成功提交，流式处理器才能发送已保存的最终结果。
        return result

    async def get(self, user, project_id, draft_id):
        async with self.sessions() as session:
            return self.view(
                await self.require_draft(session, user, project_id, draft_id)
            )

    async def list(self, user, project_id, offset=0, limit=20):
        self.require_member(user)
        async with self.sessions() as session:
            await require_document_project(session, user.id, project_id)
            condition = (
                PlanDraftDO.project_id == project_id,
                PlanDraftDO.owner_id == user.id,
            )
            total = await session.scalar(
                select(func.count(PlanDraftDO.id)).where(*condition)
            )
            drafts = await session.scalars(
                select(PlanDraftDO)
                .where(*condition)
                .order_by(PlanDraftDO.created_at.desc(), PlanDraftDO.id)
                .offset(offset)
                .limit(limit)
            )
            return PlanDraftPageVO(
                items=[self.view(draft) for draft in drafts],
                total=total or 0,
                offset=offset,
                limit=limit,
            )

    async def update(self, user, project_id, draft_id, body: DraftUpdateQO):
        try:
            async with self.sessions.begin() as session:
                draft = await self.require_draft(
                    session, user, project_id, draft_id, lock=True
                )
                self.check_version(draft, body.version)
                if draft.conversation_id:
                    raise ApiError(
                        409, "draft_already_submitted", "草案已提交，不能继续修改"
                    )
                plan = PlanResultVO.model_validate(draft.plan)
                self.check_sources(plan, body.proposal)
                draft.plan = {
                    **draft.plan,
                    "proposal": body.proposal.model_dump(mode="json"),
                }
                draft.version += 1
                await session.flush()
                await session.refresh(draft)
                result = self.view(draft)
            return result
        except StaleDataError as exc:
            raise ApiError(
                409, "draft_version_conflict", "草案已被修改，请载入最新草案后核对"
            ) from exc

    async def submit(
        self,
        user,
        project_id,
        draft_id,
        body: DraftSubmitQO,
        *,
        events: EventPublisher = NOOP_EVENTS,
    ):
        self.require_member(user)
        # 进程锁覆盖同一草案的重试；数据库行锁保证送审绑定事务串行执行。
        async with self.approvals.execution_lock(draft_id):
            async with self.sessions.begin() as session:
                await self.lock_project(session, user, project_id)
                draft = await self.require_draft(
                    session, user, project_id, draft_id, lock=True
                )
                self.check_version(draft, body.version)
                if draft.conversation_id is None:
                    plan = PlanResultVO.model_validate(draft.plan)
                    self.check_sources(plan, plan.proposal)
                    hashes = await self.approvals.document_hashes(
                        session, project_id, plan
                    )
                    if hashes != draft.document_hashes:
                        raise ApiError(
                            409,
                            "draft_documents_changed",
                            "引用的资料已变化，请重新生成草案",
                        )
                    titles = await session.scalars(
                        select(TaskDO.title).where(TaskDO.project_id == project_id)
                    )
                    existing = {normalize_task_title(title) for title in titles}
                    if any(
                        normalize_task_title(task.title) in existing
                        for task in plan.proposal.tasks
                    ):
                        raise ApiError(
                            409,
                            "draft_task_conflict",
                            "看板已有同名任务，请修改草案后提交",
                        )
                    conversation = ConversationDO(
                        project_id=project_id, owner_id=user.id, goal=draft.goal
                    )
                    session.add(conversation)
                    await session.flush()
                    draft.conversation_id = conversation.id
                conversation_id = draft.conversation_id
            # 即使此处断开，已绑定的会话也能重试，草案不会重新生成。
            return await self.approvals.start(user, conversation_id, events=events)
