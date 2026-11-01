from fastapi import APIRouter, Depends

from auth.deps import require_auth

router = APIRouter(tags=["eval-platform"], dependencies=[Depends(require_auth)])
from .skill_evals import router as _a; router.include_router(_a)
from .runs_eval import router as _b; router.include_router(_b)
from .kb_eval import router as _c; router.include_router(_c)
from .prompt_eval import router as _d; router.include_router(_d)
from .arena_wiring import router as _e; router.include_router(_e)
from .code_review_gold import router as _f; router.include_router(_f)
from .store_api import router as _g; router.include_router(_g)  # EVAL_V1 E2
