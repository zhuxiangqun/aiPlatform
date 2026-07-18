u"""
Ontology Editor API router — platform-layer REST endpoints.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/ontology-editor", tags=["ontology-editor"])

from .domain_crud import router as _domain_router
from .view_crud import router as _view_router
from .monitor_crud import router as _monitor_router

router.include_router(_domain_router, prefix="")
router.include_router(_view_router, prefix="")
router.include_router(_monitor_router, prefix="")
