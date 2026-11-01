from fastapi import APIRouter, Depends

from auth.deps import require_auth

router = APIRouter(tags=["diagnosis-platform"], dependencies=[Depends(require_auth)])
from .cases import router as _cases  # noqa: E402

router.include_router(_cases)
