"""Org L5 module router."""
from fastapi import APIRouter, Depends

from auth.deps import require_auth
from .routes import router as _org_routes

router = APIRouter(tags=["org-l5"], dependencies=[Depends(require_auth)])
router.include_router(_org_routes)
