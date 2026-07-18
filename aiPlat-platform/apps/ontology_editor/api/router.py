u"""
Ontology Editor API router — platform-layer REST endpoints.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/ontology-editor", tags=["ontology-editor"])

from .domain_crud import router as _domain_router

router.include_router(_domain_router, prefix="")
