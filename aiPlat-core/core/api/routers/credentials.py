"""
Credentials API — CRUD for API keys / tokens bound to tools.

Storage: ~/.aiplat/credentials.json
Security: keys are stored as-is in the JSON file. The API returns masked keys
          (first 4 + last 4 chars, middle masked) unless the full-key endpoint
          is called with explicit confirmation.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class CredentialCreate(BaseModel):
    name: str
    key: str
    provider: str = ""
    tool_name: str = ""


class CredentialUpdate(BaseModel):
    name: Optional[str] = None
    key: Optional[str] = None
    provider: Optional[str] = None
    tool_name: Optional[str] = None


def _storage_path() -> Path:
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    return Path(home) / "credentials.json"


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


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _mask_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with the key masked."""
    masked = dict(item)
    masked["key"] = _mask_key(item.get("key", ""))
    return masked


@router.get("/credentials")
async def list_credentials():
    items = _load()
    return {"credentials": [_mask_item(i) for i in items], "total": len(items)}


@router.post("/credentials")
async def create_credential(body: CredentialCreate):
    items = _load()
    for c in items:
        if c["name"] == body.name:
            raise HTTPException(status_code=409, detail=f"Credential '{body.name}' already exists")
    new_cred = {
        "id": f"cred_{int(time.time() * 1000)}",
        "name": body.name,
        "key": body.key,
        "provider": body.provider,
        "tool_name": body.tool_name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    items.append(new_cred)
    _save(items)
    return _mask_item(new_cred)


@router.get("/credentials/{credential_id}")
async def get_credential(credential_id: str, reveal: bool = Query(False)):
    for c in _load():
        if c["id"] == credential_id:
            if reveal:
                return c  # full key
            return _mask_item(c)
    raise HTTPException(status_code=404, detail="Credential not found")


@router.put("/credentials/{credential_id}")
async def update_credential(credential_id: str, body: CredentialUpdate):
    items = _load()
    for i, c in enumerate(items):
        if c["id"] == credential_id:
            if body.name is not None:
                c["name"] = body.name
            if body.key is not None:
                c["key"] = body.key
            if body.provider is not None:
                c["provider"] = body.provider
            if body.tool_name is not None:
                c["tool_name"] = body.tool_name
            c["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _save(items)
            return _mask_item(c)
    raise HTTPException(status_code=404, detail="Credential not found")


@router.delete("/credentials/{credential_id}")
async def delete_credential(credential_id: str):
    items = _load()
    filtered = [c for c in items if c["id"] != credential_id]
    if len(filtered) == len(items):
        raise HTTPException(status_code=404, detail="Credential not found")
    _save(filtered)
    return {"status": "deleted"}
