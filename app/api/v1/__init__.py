from fastapi import APIRouter
from app.api.v1 import auth, notebooks, admin, deployments, model_versions, github, webhooks

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router)
router.include_router(notebooks.router)
router.include_router(deployments.router)
router.include_router(admin.router)
router.include_router(model_versions.router)
router.include_router(github.router)
router.include_router(webhooks.router)