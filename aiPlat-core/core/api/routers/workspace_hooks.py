"""Workspace hooks — scan and manage ~/.aiplat/hooks/*.py files."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

router = APIRouter()


def _hooks_dir() -> Path:
    return Path.home() / ".aiplat" / "hooks"


def _list_hook_files() -> List[Dict[str, Any]]:
    base = _hooks_dir()
    if not base.exists():
        return []
    items = []
    for f in sorted(base.glob("*.py")):
        items.append({
            "name": f.stem,
            "file": str(f),
            "size": f.stat().st_size,
            "enabled": True,  # all workspace hooks are enabled by default
        })
    return items


@router.get("/workspace/hooks", response_model=Dict[str, Any])
async def list_workspace_hooks():
    """List workspace hooks (~/.aiplat/hooks)."""
    return {"items": _list_hook_files()}


@router.get("/workspace/hooks/{name}", response_model=Dict[str, Any])
async def get_workspace_hook(name: str):
    """Get workspace hook file content."""
    base = _hooks_dir()
    hook_file = base / f"{name}.py"
    if not hook_file.exists():
        raise HTTPException(status_code=404, detail=f"Hook {name} not found")
    return {"name": name, "content": hook_file.read_text(encoding="utf-8"), "size": hook_file.stat().st_size}


@router.put("/workspace/hooks/{name}", response_model=Dict[str, Any])
async def upsert_workspace_hook(name: str, data: dict):
    """Create or update a workspace hook file."""
    base = _hooks_dir()
    base.mkdir(parents=True, exist_ok=True)
    content = (data.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    hook_file = base / f"{name}.py"
    hook_file.write_text(content, encoding="utf-8")
    return {"name": name, "status": "saved", "size": hook_file.stat().st_size}


@router.delete("/workspace/hooks/{name}", response_model=Dict[str, Any])
async def delete_workspace_hook(name: str):
    """Delete a workspace hook file."""
    base = _hooks_dir()
    hook_file = base / f"{name}.py"
    if not hook_file.exists():
        raise HTTPException(status_code=404, detail=f"Hook {name} not found")
    hook_file.unlink()
    return {"name": name, "status": "deleted"}
