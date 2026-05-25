"""builder_teams API — stub router (source was lost, regenerated)."""
from fastapi import APIRouter
from typing import Optional
router = APIRouter()

@router.get("/builder_teams")
async def stub_list(limit: int = 100, offset: int = 0):
    return {"items": [], "total": 0, "limit": limit, "offset": offset}
