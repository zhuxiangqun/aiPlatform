"""Value center API router — platform-layer re-export (v2.5 canonical)."""
from fastapi import APIRouter, Depends

from auth.deps import require_auth

router = APIRouter(tags=["value-platform"], dependencies=[Depends(require_auth)])
from .value import router as _v_router
from .roles import router as _r_router
from .safety import router as _s_router
router.include_router(_v_router)
router.include_router(_r_router)
router.include_router(_s_router)
