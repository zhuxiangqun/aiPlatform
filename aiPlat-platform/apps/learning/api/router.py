from fastapi import APIRouter, Depends

from auth.deps import require_auth

router = APIRouter(tags=["learning-platform"], dependencies=[Depends(require_auth)])
from .learning_releases import router as _a; router.include_router(_a)
from .learning_autocapture import router as _b; router.include_router(_b)
from .learning_misc import router as _c; router.include_router(_c)
