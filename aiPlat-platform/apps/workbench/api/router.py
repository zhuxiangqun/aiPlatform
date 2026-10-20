"""Workbench API router — platform-layer re-export (v2.5 canonical)."""
from fastapi import APIRouter, Depends

from auth.deps import require_auth

router = APIRouter(tags=["workbench-platform"], dependencies=[Depends(require_auth)])

from .workbench import router as _w_router
from .overview import router as _o_router
from .kanban import router as _k_router

router.include_router(_w_router)
router.include_router(_o_router)
router.include_router(_k_router)
