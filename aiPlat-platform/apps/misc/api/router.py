from fastapi import APIRouter
router = APIRouter(tags=["misc-platform"])
from .finetune import router as _a; router.include_router(_a)
from .browser_test import router as _b; router.include_router(_b)
from .code_intel import router as _c; router.include_router(_c)
from .personas import router as _d; router.include_router(_d)
from .catalog import router as _e; router.include_router(_e)
from .playbook import router as _f; router.include_router(_f)
from .autosmoke import router as _g; router.include_router(_g)
