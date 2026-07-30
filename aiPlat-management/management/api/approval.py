"""
审批中心 API（通过 Core API 代理操作 workspace agent）

- GET  /approval/list     列出所有可审批内容
- POST /approval/approve   ready → published (功能审核通过)
- POST /approval/list      published → listed (上架审核通过)
- POST /approval/reject    ready → draft
- POST /approval/deprecate listed/published → deprecated
"""
import asyncio
import logging
import os
from typing import Dict
from fastapi import APIRouter, HTTPException, Query
import httpx

router = APIRouter(prefix="", tags=["approval"])
logger = logging.getLogger(__name__)

CORE_BASE = os.environ.get("AIPLAT_CORE_API_URL", "http://localhost:8002/api/core")


async def _core_put(path: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.put(f"{CORE_BASE}{path}", json=data)
        if resp.status_code >= 400:
            detail = "Unknown error"
            try:
                detail = resp.json().get("detail", detail)
            except Exception:
                detail = resp.text[:200]
            raise HTTPException(status_code=resp.status_code, detail=detail)
        return resp.json()


async def _core_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{CORE_BASE}{path}", params=params or {})
        if resp.status_code != 200:
            return {"agents": []}
        return resp.json()


@router.get("/approval/list")
async def list_items():
    """列出所有 workspace agent/skill/mcp/workflow 及状态"""
    items = []

    # Agents
    try:
        data = await _core_get("/workspace/agents?limit=200")
        agents = data.get("agents", []) if isinstance(data, dict) else []
        # Collect all referenced skill IDs for batch status lookup
        all_skill_ids = set()
        for a in agents:
            for sid in (a.get("skills") or []):
                all_skill_ids.add(sid)

        # Fetch skill statuses
        skill_statuses: Dict[str, str] = {}
        engine_skills: set[str] = set()

        # Also get engine skills (always available, no approval needed)
        try:
            es_data = await _core_get("/skills?limit=500")
            for sk in (es_data.get("skills", []) if isinstance(es_data, dict) else []):
                nm = sk.get("name", "")
                sid = sk.get("id", "")
                if sid:
                    engine_skills.add(sid)
                    skill_statuses[sid] = "listed"
                if nm and nm != sid:
                    engine_skills.add(nm)
                    skill_statuses[nm] = "listed"
        except Exception:
            logger.warning("Failed to fetch engine skills for approval list", exc_info=True)

        if all_skill_ids:
            try:
                sd = await _core_get("/workspace/skills?limit=500&ids=" + ",".join(all_skill_ids))
                for s in (sd.get("skills", []) if isinstance(sd, dict) else []):
                    key = s.get("id", "") or s.get("name", "")
                    if key and key not in engine_skills:
                        skill_statuses[key] = s.get("status", "draft")
            except Exception:
                logger.warning("Failed to fetch workspace skill details for approval list", exc_info=True)

        for a in agents:
            deps = []
            for sid in (a.get("skills") or [])[:5]:
                s = skill_statuses.get(sid, "unknown")
                if sid in engine_skills:
                    s = "listed"  # engine skills always OK
                if s not in ("published", "listed"):
                    deps.append(f"skill:{sid}({s})")
            items.append({
                "id": a.get("id", ""),
                "name": a.get("display_name", "") or a.get("name", ""),
                "type": "agent",
                "status": a.get("status", "draft"),
                "description": a.get("description", "") or a.get("metadata", {}).get("description", ""),
                "skills": a.get("skills", []),
                "tools": a.get("tools", []),
                "agent_type": a.get("agent_type", ""),
                "deps_ok": len(deps) == 0,
                "dep_warnings": deps,
                "meta": {
                    "model": (a.get("config", {}) or {}).get("model", "") or a.get("metadata", {}).get("model", ""),
                    "system_prompt": (a.get("config", {}) or {}).get("system_prompt", ""),
                    "sop_steps": 0,
                    "mcp_ids": a.get("mcp_ids", []) or [],
                    "workflow_ids": a.get("workflow_ids", []) or [],
                    "governance": (a.get("metadata", {}) or {}).get("governance", {}),
                    "lint": (a.get("metadata", {}) or {}).get("governance", {}).get("lint_result", {}),
                },
            })
    except Exception:
        logger.warning("Failed to build agent approval items", exc_info=True)

    # Skills
    try:
        sd = await _core_get("/workspace/skills?limit=500")
        skills = sd.get("skills", []) if isinstance(sd, dict) else []
        for s in skills:
            items.append({
                "id": s.get("id", ""),
                "name": s.get("display_name", "") or s.get("name", ""),
                "type": "skill",
                "status": s.get("status", "draft"),
                "description": s.get("description", ""),
                "skills": [],
                "tools": [],
                "agent_type": "",
                "deps_ok": True,
                "dep_warnings": [],
                "meta": {
                    "transport": s.get("transport", ""),
                    "url": s.get("url", ""),
                    "governance": (s.get("metadata", {}) or {}).get("governance", {}),
                    "lint": (s.get("metadata", {}) or {}).get("governance", {}).get("lint_result", {}),
                },
            })
    except Exception:
        logger.warning("Failed to build skill approval items", exc_info=True)

    # MCP servers
    try:
        md = await _core_get("/workspace/mcp/servers")
        servers = md.get("servers", []) if isinstance(md, dict) else []
        for s in servers:
            items.append({
                "id": s.get("name", "") or s.get("id", ""),
                "name": s.get("display_name", "") or s.get("name", "") or s.get("id", ""),
                "type": "mcp",
                "status": s.get("status", "draft"),
                "description": s.get("description", ""),
                "skills": [],
                "tools": [],
                "agent_type": "",
                "deps_ok": True,
                "dep_warnings": [],
                "meta": {
                    "transport": s.get("transport", ""),
                    "tool_count": len(s.get("tools", []) if isinstance(s.get("tools"), list) else []),
                },
            })
    except Exception:
        logger.warning("Failed to build MCP server approval items", exc_info=True)

    # Workflow templates
    try:
        wd = await _core_get("/workflow/templates")
        workflows = wd.get("templates", []) if isinstance(wd, dict) else (wd.get("workflows", []) if isinstance(wd, dict) else [])
        if not isinstance(workflows, list):
            workflows = []
        for w in workflows:
            items.append({
                "id": w.get("id", "") or w.get("name", ""),
                "name": w.get("display_name", "") or w.get("name", "") or w.get("id", ""),
                "type": "workflow",
                "status": w.get("status", "draft"),
                "description": w.get("description", ""),
                "skills": [],
                "tools": [],
                "agent_type": "",
                "deps_ok": True,
                "dep_warnings": [],
                "meta": {
                    "node_count": len(w.get("nodes", []) if isinstance(w.get("nodes"), list) else []),
                    "edge_count": len(w.get("edges", []) if isinstance(w.get("edges"), list) else []),
                    "bound_app": w.get("app", ""),
                    "governance": (w.get("_governance", {}) or {}),
                    "lint": (w.get("_governance", {}) or {}).get("lint_result", {}),
                },
            })
    except Exception:
        logger.warning("Failed to build workflow template approval items", exc_info=True)

    return {
        "items": items,
        "pending_func": [i for i in items if i["status"] == "ready"],
        "pending_list": [i for i in items if i["status"] == "published"],
        "listed": [i for i in items if i["status"] == "listed"],
        "deprecated": [i for i in items if i["status"] == "deprecated"],
    }


def _update_path(item_id: str, item_type: str) -> str:
    """Get the core API update path for each item type."""
    paths = {
        "agent": f"/workspace/agents/{item_id}",
        "skill": f"/workspace/skills/{item_id}",
        "mcp": f"/workspace/mcp/servers/{item_id}",
        "workflow": f"/workflow/templates/{item_id}",
    }
    return paths.get(item_type, paths["agent"])


@router.post("/approval/approve")
async def approve_item(id: str = Query(...), type: str = Query("agent")):
    """功能审核: ready → published"""
    path = _update_path(id, type)
    await _core_put(path, {"status": "published"})
    return {"ok": True, "id": id, "type": type, "status": "published"}


@router.post("/approval/publish")
async def publish_item(id: str = Query(...), type: str = Query("agent")):
    """上架审核: published → listed"""
    path = _update_path(id, type)
    await _core_put(path, {"status": "listed"})
    return {"ok": True, "id": id, "type": type, "status": "listed"}


@router.post("/approval/reject")
async def reject_item(id: str = Query(...), type: str = Query("agent")):
    """退回: ready → draft"""
    path = _update_path(id, type)
    await _core_put(path, {"status": "draft"})
    return {"ok": True, "id": id, "type": type, "status": "draft"}


@router.post("/approval/unlist")
async def unlist_item(id: str = Query(...), type: str = Query("agent")):
    """下架: listed → published"""
    path = _update_path(id, type)
    await _core_put(path, {"status": "published"})
    return {"ok": True, "id": id, "type": type, "status": "published"}


@router.post("/approval/deprecate")
async def deprecate_item(id: str = Query(...), type: str = Query("agent")):
    """废弃: published → deprecated"""
    path = _update_path(id, type)
    await _core_put(path, {"status": "deprecated"})
    return {"ok": True, "id": id, "type": type, "status": "deprecated"}


@router.get("/approval/history")
async def approval_history(limit: int = Query(50)):
    """审批操作记录 — approver 可查看自己的审批历史。"""
    items = []
    # Agents
    try:
        data = await _core_get("/workspace/agents?limit=200")
        agents = data.get("agents", []) if isinstance(data, dict) else []
        for a in agents:
            st = a.get("status", "")
            if st in ("published", "listed", "deprecated"):
                items.append({
                    "id": a.get("id", ""), "name": a.get("display_name", "") or a.get("name", ""),
                    "type": "agent", "status": st,
                    "description": a.get("description", "")[:100],
                })
    except Exception:
        pass  # noqa: intentional — best-effort non-critical operation
    # Skills
    try:
        data = await _core_get("/workspace/skills?limit=200")
        skills = data.get("skills", []) if isinstance(data, dict) else []
        for s in skills:
            st = s.get("status", "")
            if st in ("published", "listed", "deprecated"):
                items.append({
                    "id": s.get("id", ""), "name": s.get("name", ""),
                    "type": "skill", "status": st,
                    "description": s.get("description", "")[:100],
                })
    except Exception:
        pass  # noqa: intentional — best-effort non-critical operation
    items.sort(key=lambda x: x.get("status", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


