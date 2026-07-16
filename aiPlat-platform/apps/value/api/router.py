"""Value center API router — platform-layer re-export (v2.5 transitional)."""
from fastapi import APIRouter

router = APIRouter(tags=["value-platform"])
from .value import router as _v_router
from .roles import router as _r_router
from .safety import router as _s_router
router.include_router(_v_router)
router.include_router(_r_router)
router.include_router(_s_router)
