u"""
Ontology Editor API router — platform-layer REST endpoints.

When ``AIPLAT_API_KEY`` / ``AIPLAT_ADMIN_KEY`` is set, every route requires
``require_auth`` (same as other platform apps modules).
"""
from fastapi import APIRouter, Depends

from auth.deps import require_auth

router = APIRouter(
    prefix="/ontology-editor",
    tags=["ontology-editor"],
    dependencies=[Depends(require_auth)],
)

from .domain_crud import router as _domain_router
from .view_crud import router as _view_router
from .monitor_crud import router as _monitor_router
from .metric_crud import router as _metric_router
from .scoring_crud import router as _scoring_router
from .scenario_crud import router as _scenario_router
from .governance_crud import router as _governance_router

router.include_router(_domain_router, prefix="")
router.include_router(_view_router, prefix="")
router.include_router(_monitor_router, prefix="")
router.include_router(_metric_router, prefix="")
router.include_router(_scoring_router, prefix="")
router.include_router(_scenario_router, prefix="")
router.include_router(_governance_router)  # governance_crud 自带 prefix="/governance"
