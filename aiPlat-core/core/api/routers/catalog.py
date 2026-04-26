from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()


def _store(rt):
    return getattr(rt, "execution_store", None) if rt else None


def _skill_mgr(rt):
    return getattr(rt, "skill_manager", None) if rt else None


def _ws_skill_mgr(rt):
    return getattr(rt, "workspace_skill_manager", None) if rt else None


@router.get("/catalog/skills")
async def list_skill_catalog(
    q: Optional[str] = None,
    scope: str = "all",  # all|engine|workspace
    skill_kind: Optional[str] = None,
    tag: Optional[str] = None,
    tenant_id: Optional[str] = None,
    include_usage: bool = True,
    usage_lookback_days: int = 30,
    limit: int = 200,
    offset: int = 0,
    rt=Depends(get_kernel_runtime),
):
    """
    Minimal Skill Catalog (M2):
    - Lists engine + workspace skills with basic filtering
    - Optionally adds usage_count derived from syscall_events(kind=skill) over a lookback window
    """
    store = _store(rt)
    if not rt or not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    scope = str(scope or "all").strip().lower()
    if scope not in {"all", "engine", "workspace"}:
        scope = "all"
    q0 = str(q or "").strip().lower()
    kind0 = str(skill_kind or "").strip().lower() if skill_kind else None
    tag0 = str(tag or "").strip().lower() if tag else None

    skills: List[Dict[str, Any]] = []

    async def _scan(mgr: Any, sc: str) -> None:
        if mgr is None:
            return
        try:
            items = await mgr.list_skills(None, None, 1000, 0)
        except Exception:
            items = []
        for s in items or []:
            meta = getattr(s, "metadata", None)
            meta = meta if isinstance(meta, dict) else {}
            item = {
                "skill_id": str(getattr(s, "id", "") or ""),
                "name": str(getattr(s, "name", "") or ""),
                "description": str(getattr(s, "description", "") or ""),
                "scope": sc,
                "skill_kind": str(meta.get("skill_kind") or "rule"),
                "tags": meta.get("tags") if isinstance(meta.get("tags"), list) else [],
                "trigger_conditions": meta.get("trigger_conditions") or [],
                "capabilities": meta.get("capabilities") if isinstance(meta.get("capabilities"), list) else [],
            }
            skills.append(item)

    if scope in {"all", "workspace"}:
        await _scan(_ws_skill_mgr(rt), "workspace")
    if scope in {"all", "engine"}:
        await _scan(_skill_mgr(rt), "engine")

    # Filtering
    out: List[Dict[str, Any]] = []
    for s in skills:
        if kind0 and str(s.get("skill_kind") or "").lower() != kind0:
            continue
        if tag0:
            tags = [str(x).lower() for x in (s.get("tags") or []) if isinstance(x, str)]
            if tag0 not in tags:
                continue
        if q0:
            hay = f"{s.get('skill_id','')} {s.get('name','')} {s.get('description','')}".lower()
            if q0 not in hay:
                continue
        out.append(s)

    # Usage stats (best-effort): scan recent skill syscalls and count by "name"
    usage_map: Dict[str, int] = {}
    if include_usage:
        since_ts = time.time() - float(max(1, int(usage_lookback_days or 30))) * 86400.0
        try:
            ev = await store.list_syscall_events(limit=5000, offset=0, tenant_id=tenant_id, kind="skill")
            for it in (ev.get("items") or []):
                if not isinstance(it, dict):
                    continue
                try:
                    if float(it.get("created_at") or 0) < since_ts:
                        continue
                except Exception:
                    continue
                nm = str(it.get("name") or "")
                if nm:
                    usage_map[nm] = usage_map.get(nm, 0) + 1
        except Exception:
            usage_map = {}

    # Pagination
    total = len(out)
    out2 = out[int(offset or 0) : int(offset or 0) + int(limit or 200)]
    if include_usage:
        for s in out2:
            s["usage_count"] = int(usage_map.get(str(s.get("name") or ""), 0))

    return {"status": "ok", "total": total, "items": out2}

