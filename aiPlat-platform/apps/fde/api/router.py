"""
FDE API router — platform-layer REST endpoints for Field Deployment Engineer.

v2.5 Transitional: delegates all routes to core/api/routers/fde.py.
Gradually moving implementations here per router-migration-plan.md.

Once migration is complete, this file will contain all @router.get/post
definitions directly.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/fde", tags=["fde-platform"])

# ── Transitional — import from current core location ──
# When a sub-router (e.g. fde_acceptance.py) is fully moved to 
# platform/apps/fde/api/, uncomment its direct include below.

from core.api.routers.fde import router as _core_fde_router
from core.api.routers.fde_acceptance import router as _acceptance_router
from core.api.routers.fde_manuals import router as _manuals_router
from core.api.routers.fde_delivery import router as _delivery_router
from core.api.routers.fde_handover_v2 import router as _handover_router
from core.api.routers.fde_sessions_v2 import router as _sessions_router
from core.api.routers.fde_reports import router as _reports_router
from core.api.routers.fde_ask import router as _ask_router
from core.api.routers.fde_validate import router as _validate_router
from core.api.routers.fde_governance import router as _governance_router
from core.api.routers.fde_bootstrap import router as _bootstrap_router
from core.api.routers.fde_dashboard_v2 import router as _dashboard_router
from core.api.routers.fde_diagnostics_v2 import router as _diag_router
from core.api.routers.fde_domain_ops import router as _domain_ops_router
from core.api.routers.fde_maintenance import router as _maintenance_router
from core.api.routers.fde_overview import router as _overview_router
from core.api.routers.fde_pipeline import router as _pipeline_router
from core.api.routers.fde_quality_summary import router as _quality_router
from core.api.routers.fde_sessions_compare import router as _compare_router
from core.api.routers.fde_trends import router as _trends_router

# Mount all sub-routers
router.include_router(_core_fde_router)
router.include_router(_acceptance_router)
router.include_router(_manuals_router)
router.include_router(_delivery_router)
router.include_router(_handover_router)
router.include_router(_sessions_router)
router.include_router(_reports_router)
router.include_router(_ask_router)
router.include_router(_validate_router)
router.include_router(_governance_router)
router.include_router(_bootstrap_router)
router.include_router(_dashboard_router)
router.include_router(_diag_router)
router.include_router(_domain_ops_router)
router.include_router(_maintenance_router)
router.include_router(_overview_router)
router.include_router(_pipeline_router)
router.include_router(_quality_router)
router.include_router(_compare_router)
router.include_router(_trends_router)
