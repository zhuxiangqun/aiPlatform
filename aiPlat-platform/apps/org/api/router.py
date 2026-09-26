"""Org L5 module router."""
from fastapi import APIRouter

from .routes import router as _org_routes

router = APIRouter(tags=["org-l5"])
router.include_router(_org_routes)
