from fastapi import APIRouter, Depends

from auth.deps import require_auth

router = APIRouter(tags=["prompt-platform"], dependencies=[Depends(require_auth)])
from .prompt_templates import router as _a; router.include_router(_a)
from .prompt_app import router as _b; router.include_router(_b)
from .prompt_optimize import router as _c; router.include_router(_c)
