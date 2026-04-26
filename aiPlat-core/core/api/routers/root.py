from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root():
    """Root endpoint"""
    return {"message": "aiPlat-core API", "version": "0.1.0"}

