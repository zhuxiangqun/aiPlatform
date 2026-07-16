"""
FDE API router — platform-layer REST endpoints for Field Deployment Engineer.

v2.5 Phase 1: All 20 sub-routers copied to platform/apps/fde/api/.
Imports from local copies; core originals retained for backward compat.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/fde", tags=["fde-platform"])

# ── Local imports (all 20 sub-routers) ──
from .fde import router as _fde_router
from .fde_overview import router as _overview_router
from .fde_ask import router as _ask_router
from .fde_validate import router as _validate_router
from .fde_trends import router as _trends_router
from .fde_delivery import router as _delivery_router
from .fde_pipeline import router as _pipeline_router
from .fde_bootstrap import router as _bootstrap_router
from .fde_manuals import router as _manuals_router
from .fde_acceptance import router as _acceptance_router
from .fde_handover_v2 import router as _handover_router
from .fde_sessions_v2 import router as _sessions_router
from .fde_reports import router as _reports_router
from .fde_governance import router as _governance_router
from .fde_dashboard_v2 import router as _dashboard_router
from .fde_diagnostics_v2 import router as _diag_router
from .fde_domain_ops import router as _domain_ops_router
from .fde_maintenance import router as _maintenance_router
from .fde_quality_summary import router as _quality_router
from .fde_sessions_compare import router as _compare_router

# ── Mount all ──
router.include_router(_fde_router)
router.include_router(_overview_router)
router.include_router(_ask_router)
router.include_router(_validate_router)
router.include_router(_trends_router)
router.include_router(_delivery_router)
router.include_router(_pipeline_router)
router.include_router(_bootstrap_router)
router.include_router(_manuals_router)
router.include_router(_acceptance_router)
router.include_router(_handover_router)
router.include_router(_sessions_router)
router.include_router(_reports_router)
router.include_router(_governance_router)
router.include_router(_dashboard_router)
router.include_router(_diag_router)
router.include_router(_domain_ops_router)
router.include_router(_maintenance_router)
router.include_router(_quality_router)
router.include_router(_compare_router)
