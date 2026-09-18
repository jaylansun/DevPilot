from fastapi import APIRouter

from app.api.v1.auth_controller import router as auth_router
from app.api.v1.document_controller import router as documents_router
from app.api.v1.plan_controller import router as plan_router
from app.api.v1.project_controller import router as projects_router
from app.api.v1.rag_controller import router as rag_router
from app.api.v1.task_controller import router as tasks_router
from app.api.v1.workflow_controller import router as workflow_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(projects_router)
router.include_router(tasks_router)
router.include_router(documents_router)
router.include_router(rag_router)
router.include_router(plan_router)
router.include_router(workflow_router)

__all__ = ["router"]
