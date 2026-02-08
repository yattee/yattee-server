"""Admin web UI and API endpoints."""

from fastapi import APIRouter

from .pages import router as pages_router
from .settings import router as settings_router
from .sites import router as sites_router
from .users import router as users_router

router = APIRouter(tags=["admin"])
router.include_router(pages_router)
router.include_router(users_router)
router.include_router(sites_router)
router.include_router(settings_router)
