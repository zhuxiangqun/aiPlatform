from __future__ import annotations
from typing import Dict, Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/", response_model=Dict[str, Any])
async def root():
    """Root endpoint"""
    return {"message": "aiPlat-core API", "version": "0.1.0"}

