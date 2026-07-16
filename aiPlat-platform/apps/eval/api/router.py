from fastapi import APIRouter
router = APIRouter(tags=["eval-platform"])
from .skill_evals import router as _a; router.include_router(_a)
from .runs_eval import router as _b; router.include_router(_b)
from .kb_eval import router as _c; router.include_router(_c)
from .prompt_eval import router as _d; router.include_router(_d)
