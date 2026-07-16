"""
FDE API router — platform-layer REST endpoints for Field Deployment Engineer.

v2.5 Transition: currently delegates to core/api/routers/fde.py.
Gradually moving implementations here per router-migration-plan.md.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/fde", tags=["fde", "fde-platform"])


def _get_fde_router():
    """Lazy import the FDE router from its current location."""
    from core.api.routers.fde import router as _fde_router
    return _fde_router


# ── Transitional: delegate all FDE routes to the core router ──
# Once all sub-routers are moved to platform/apps/fde/api/,
# remove this delegation and register them directly here.

@router.on_event("startup")
async def _setup():
    """Mount the core FDE router during transition."""
    pass  # delegation handled in include below


# Export the router for platform server registration
__all__ = ["router"]
