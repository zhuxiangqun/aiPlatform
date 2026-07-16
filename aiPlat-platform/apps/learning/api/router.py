from fastapi import APIRouter
router = APIRouter(tags=["learning-platform"])
from .learning_releases import router as _a; router.include_router(_a)
from .learning_autocapture import router as _b; router.include_router(_b)
from .learning_misc import router as _c; router.include_router(_c)
