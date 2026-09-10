from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi import FastAPI

from app.api.dependencies import get_current_user
from app.api.error_handlers import register_error_handlers
from app.api.v1.project_controller import router as projects_router
from app.api.v1.task_controller import router as tasks_router
from app.database import get_db_session
from app.middleware import request_id_middleware
from app.models.user_do import UserDO, UserRole


@pytest.fixture
def member_user() -> UserDO:
    return UserDO(
        id=uuid4(),
        username="member_test",
        password_hash="测试哈希",
        role=UserRole.MEMBER,
    )


@pytest.fixture
def reviewer_user() -> UserDO:
    return UserDO(
        id=uuid4(),
        username="reviewer_test",
        password_hash="测试哈希",
        role=UserRole.REVIEWER,
    )


@pytest.fixture
def api_app_factory() -> Callable[[UserDO | None], FastAPI]:
    def create_app(current_user: UserDO | None) -> FastAPI:
        app = FastAPI()
        app.middleware("http")(request_id_middleware)
        register_error_handlers(app)
        app.include_router(projects_router, prefix="/api/v1")
        app.include_router(tasks_router, prefix="/api/v1")

        async def override_database_session():
            yield object()

        app.dependency_overrides[get_db_session] = override_database_session

        if current_user is not None:
            async def override_current_user() -> UserDO:
                return current_user

            app.dependency_overrides[get_current_user] = override_current_user

        return app

    return create_app
