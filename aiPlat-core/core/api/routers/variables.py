"""
Variables API — CRUD for template variables (global + workflow scope).

Storage: ~/.aiplat/variables.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class VariableCreate(BaseModel):
    name: str
    value: str = ""
    scope: str = "global"  # "global" | "workflow"
    description: str = ""


class VariableUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    scope: Optional[str] = None
    description: Optional[str] = None


def _storage_path() -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    return Path(home) / "variables.json"


def _load() -> List[Dict[str, Any]]:
    p = _storage_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(data: List[Dict[str, Any]]) -> None:
    p = _storage_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/variables")
async def list_variables(scope: Optional[str] = None):
    items = _load()
    if scope:
        items = [v for v in items if v.get("scope") == scope]
    return {"variables": items, "total": len(items)}


@router.post("/variables")
async def create_variable(body: VariableCreate):
    items = _load()
    for v in items:
        if v["name"] == body.name:
            raise HTTPException(status_code=409, detail=f"Variable '{body.name}' already exists")
    new_var = {
        "id": f"var_{int(time.time() * 1000)}",
        "name": body.name,
        "value": body.value,
        "scope": body.scope,
        "description": body.description,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    items.append(new_var)
    _save(items)
    return new_var


@router.get("/variables/{variable_id}")
async def get_variable(variable_id: str):
    for v in _load():
        if v["id"] == variable_id:
            return v
    raise HTTPException(status_code=404, detail="Variable not found")


@router.put("/variables/{variable_id}")
async def update_variable(variable_id: str, body: VariableUpdate):
    items = _load()
    for i, v in enumerate(items):
        if v["id"] == variable_id:
            if body.name is not None:
                v["name"] = body.name
            if body.value is not None:
                v["value"] = body.value
            if body.scope is not None:
                v["scope"] = body.scope
            if body.description is not None:
                v["description"] = body.description
            v["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _save(items)
            return v
    raise HTTPException(status_code=404, detail="Variable not found")


@router.delete("/variables/{variable_id}")
async def delete_variable(variable_id: str):
    items = _load()
    filtered = [v for v in items if v["id"] != variable_id]
    if len(filtered) == len(items):
        raise HTTPException(status_code=404, detail="Variable not found")
    _save(filtered)
    return {"status": "deleted"}
