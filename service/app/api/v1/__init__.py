from fastapi import APIRouter

from app.api.v1.auth_controller import router as auth_router
from app.api.v1.project_controller import router as projects_router
from app.api.v1.task_controller import router as tasks_router


router = APIRouter()
router.include_router(auth_router)
router.include_router(projects_router)
router.include_router(tasks_router)

__all__ = ["router"]
