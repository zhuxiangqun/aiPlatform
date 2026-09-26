"""
审批中心 API（通过 Core API 代理操作 workspace agent）

- GET  /approval/list     列出所有可审批内容
- POST /approval/approve   ready → published (功能审核通过)
- POST /approval/publish   published → listed (上架审核通过；Agent 依赖硬门禁)
- POST /approval/reject    ready → draft
- POST /approval/deprecate listed/published → deprecated
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Set

from fastapi import APIRouter, HTTPException, Query
import httpx

router = APIRouter(prefix="", tags=["approval"])
logger = logging.getLogger(__name__)

CORE_BASE = os.environ.get("AIPLAT_CORE_API_URL", "http://localhost:8002/api/core")

_OK_LIFECYCLE = frozenset({"published", "listed"})


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
            return {}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _str_id(v: Any) -> str:
    return str(v).strip() if isinstance(v, str) and str(v).strip() else ""


def _record_skill_status(skill_statuses: Dict[str, str], key: str, status: str, *, overwrite: bool) -> None:
    if not key:
        return
    if overwrite or key not in skill_statuses:
        skill_statuses[key] = status


async def _load_dep_catalog() -> Dict[str, Any]:
    """Load skill / MCP / tool catalogs used for agent dependency checks.

    Workspace skill lifecycle is authoritative. Engine-only skills (not present in
    the workspace catalog) count as always available (treated as listed). A skill
    that exists in both must NOT be auto-promoted by engine membership — otherwise
    legacy workspace status like ``enabled`` bypasses the Agent 上架硬门禁.

    Tools use the same published|listed gate via ``tool_statuses`` (lifecycle store).
    """
    skill_statuses: Dict[str, str] = {}
    workspace_skill_ids: Set[str] = set()
    mcp_statuses: Dict[str, str] = {}
    tool_statuses: Dict[str, str] = {}

    try:
        sd = await _core_get("/workspace/skills", params={"limit": 500})
        for s in sd.get("skills", []) or []:
            key = _str_id(s.get("id")) or _str_id(s.get("name"))
            if not key:
                continue
            st = str(s.get("status") or "draft")
            workspace_skill_ids.add(key)
            _record_skill_status(skill_statuses, key, st, overwrite=True)
            nm = _str_id(s.get("name"))
            if nm and nm != key:
                workspace_skill_ids.add(nm)
                _record_skill_status(skill_statuses, nm, st, overwrite=True)
    except Exception:
        logger.warning("Failed to fetch workspace skills for approval deps", exc_info=True)

    try:
        es_data = await _core_get("/skills", params={"limit": 500})
        for sk in es_data.get("skills", []) or []:
            sid = _str_id(sk.get("id"))
            nm = _str_id(sk.get("name"))
            # Built-in / engine-only: fill gaps only; never override workspace lifecycle.
            if sid and sid not in workspace_skill_ids:
                _record_skill_status(skill_statuses, sid, "listed", overwrite=False)
            if nm and nm != sid and nm not in workspace_skill_ids:
                _record_skill_status(skill_statuses, nm, "listed", overwrite=False)
    except Exception:
        logger.warning("Failed to fetch engine skills for approval deps", exc_info=True)

    try:
        md = await _core_get("/workspace/mcp/servers")
        for s in md.get("servers", []) or []:
            key = _str_id(s.get("name")) or _str_id(s.get("id"))
            if key:
                mcp_statuses[key] = str(s.get("status") or "draft")
    except Exception:
        logger.warning("Failed to fetch MCP servers for approval deps", exc_info=True)

    try:
        td = await _core_get("/tools", params={"limit": 500})
        for t in td.get("tools", []) or []:
            name = _str_id(t.get("name")) or _str_id(t.get("id"))
            if not name:
                continue
            if t.get("available") is False:
                tool_statuses[name] = "unavailable"
            else:
                tool_statuses[name] = str(t.get("status") or "draft")
    except Exception:
        logger.warning("Failed to fetch core tools for approval deps", exc_info=True)

    try:
        wtd = await _core_get("/workspace/tools", params={"limit": 500})
        for t in wtd.get("tools", []) or []:
            name = _str_id(t.get("name")) or _str_id(t.get("id"))
            if not name:
                continue
            if t.get("available") is False:
                tool_statuses[name] = "unavailable"
            else:
                # Workspace catalog wins when both exist.
                tool_statuses[name] = str(t.get("status") or "draft")
    except Exception:
        logger.warning("Failed to fetch workspace tools for approval deps", exc_info=True)

    return {
        "skill_statuses": skill_statuses,
        "workspace_skill_ids": workspace_skill_ids,
        "mcp_statuses": mcp_statuses,
        "tool_statuses": tool_statuses,
    }


def _agent_dep_warnings(agent: Dict[str, Any], catalog: Dict[str, Any]) -> List[str]:
    """Return human-readable unmet deps. Empty => deps_ok.

    Skill / MCP / Tool must be published or listed.
    """
    skill_statuses: Dict[str, str] = catalog.get("skill_statuses") or {}
    mcp_statuses: Dict[str, str] = catalog.get("mcp_statuses") or {}
    tool_statuses: Dict[str, str] = catalog.get("tool_statuses") or {}
    # Backward compat for older unit tests that still pass ok_tools.
    ok_tools: Set[str] = catalog.get("ok_tools") or set()
    deps: List[str] = []

    for sid in agent.get("skills") or []:
        sid = _str_id(sid)
        if not sid:
            continue
        st = skill_statuses.get(sid, "unknown")
        if st not in _OK_LIFECYCLE:
            deps.append(f"skill:{sid}({st})")

    for mid in agent.get("mcp_ids") or []:
        mid = _str_id(mid)
        if not mid:
            continue
        st = mcp_statuses.get(mid, "unknown")
        if st not in _OK_LIFECYCLE:
            deps.append(f"mcp:{mid}({st})")

    for tid in agent.get("tools") or []:
        tid = _str_id(tid)
        if not tid:
            continue
        if tool_statuses:
            st = tool_statuses.get(tid, "unknown")
            if st not in _OK_LIFECYCLE:
                deps.append(f"tool:{tid}({st})")
        elif tid not in ok_tools:
            deps.append(f"tool:{tid}(unavailable)")

    return deps


async def _fetch_agent(agent_id: str) -> Dict[str, Any]:
    data = await _core_get(f"/workspace/agents/{agent_id}")
    if not data or data.get("detail"):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return data


@router.get("/approval/list")
async def list_items():
    """列出所有 workspace agent/skill/mcp/workflow 及状态"""
    items = []
    catalog = await _load_dep_catalog()

    # Agents
    try:
        data = await _core_get("/workspace/agents", params={"limit": 200})
        agents = data.get("agents", []) if isinstance(data, dict) else []
        for a in agents:
            deps = _agent_dep_warnings(a, catalog)
            items.append({
                "id": a.get("id", ""),
                "name": a.get("display_name", "") or a.get("name", ""),
                "type": "agent",
                "status": a.get("status", "draft"),
                "description": a.get("description", "") or (a.get("metadata") or {}).get("description", ""),
                "skills": [x for x in (a.get("skills") or []) if _str_id(x)],
                "tools": [x for x in (a.get("tools") or []) if _str_id(x)],
                "agent_type": a.get("agent_type", ""),
                "deps_ok": len(deps) == 0,
                "dep_warnings": deps,
                "meta": {
                    "model": (a.get("config", {}) or {}).get("model", "") or (a.get("metadata") or {}).get("model", ""),
                    "system_prompt": (a.get("config", {}) or {}).get("system_prompt", ""),
                    "sop_steps": 0,
                    "mcp_ids": a.get("mcp_ids", []) or [],
                    "workflow_ids": a.get("workflow_ids", []) or [],
                    "governance": (a.get("metadata") or {}).get("governance", {}),
                    "lint": ((a.get("metadata") or {}).get("governance") or {}).get("lint_result", {}),
                },
            })
    except Exception:
        logger.warning("Failed to build agent approval items", exc_info=True)

    # Skills
    try:
        sd = await _core_get("/workspace/skills", params={"limit": 500})
        for s in sd.get("skills", []) or []:
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
                    "governance": (s.get("metadata") or {}).get("governance", {}),
                    "lint": ((s.get("metadata") or {}).get("governance") or {}).get("lint_result", {}),
                },
            })
    except Exception:
        logger.warning("Failed to build skill approval items", exc_info=True)

    # MCP servers
    try:
        md = await _core_get("/workspace/mcp/servers")
        for s in md.get("servers", []) or []:
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
        workflows = wd.get("templates", []) or wd.get("workflows", []) or []
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

    # Tools (engine + workspace) — same lifecycle as skills for Agent 上架硬门禁
    try:
        seen_tools: Set[str] = set()
        for path in ("/workspace/tools", "/tools"):
            td = await _core_get(path, params={"limit": 500})
            for t in td.get("tools", []) or []:
                tid = _str_id(t.get("name")) or _str_id(t.get("id"))
                if not tid or tid in seen_tools:
                    continue
                seen_tools.add(tid)
                items.append({
                    "id": tid,
                    "name": t.get("display_name") or tid,
                    "type": "tool",
                    "status": t.get("status") or "draft",
                    "description": t.get("description", "") or "",
                    "skills": [],
                    "tools": [],
                    "agent_type": "",
                    "deps_ok": True,
                    "dep_warnings": [],
                    "meta": {
                        "scope": t.get("scope") or ("workspace" if path.startswith("/workspace") else "engine"),
                        "category": t.get("category", ""),
                        "available": t.get("available", True),
                    },
                })
    except Exception:
        logger.warning("Failed to build tool approval items", exc_info=True)

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
        "tool": f"/tools/{item_id}",
    }
    return paths.get(item_type, paths["agent"])


@router.post("/approval/approve")
async def approve_item(id: str = Query(...), type: str = Query("agent")):
    """功能审核: ready → published"""
    path = _update_path(id, type)
    await _core_put(path, {"status": "published"})
    return {"ok": True, "id": id, "type": type, "status": "published"}


@router.post("/approval/submit")
async def submit_item(id: str = Query(...), type: str = Query("agent")):
    """提交审核: draft → ready（Tool 等需先进待审核队列）。"""
    if type == "tool":
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{CORE_BASE}/tools/{id}/submit-for-review")
            if resp.status_code >= 400:
                detail = "Unknown error"
                try:
                    detail = resp.json().get("detail", detail)
                except Exception:
                    detail = resp.text[:200]
                raise HTTPException(status_code=resp.status_code, detail=detail)
            data = resp.json() if resp.content else {}
            return {"ok": True, "id": id, "type": type, "status": data.get("new_status") or "ready"}
    path = _update_path(id, type)
    await _core_put(path, {"status": "ready"})
    return {"ok": True, "id": id, "type": type, "status": "ready"}


async def _submit_item_impl(id: str, type: str = "agent") -> Dict[str, Any]:
    """Internal entry so submit_item has a same-module production caller."""
    return await submit_item(id=id, type=type)


@router.post("/approval/publish")
async def publish_item(id: str = Query(...), type: str = Query("agent")):
    """上架审核: published → listed。

    Agent 硬门禁：skills / mcp_ids / tools 未就绪则拒绝上架。
    Skill/MCP/Workflow 本身无此类依赖门禁。
    """
    if type == "agent":
        agent = await _fetch_agent(id)
        catalog = await _load_dep_catalog()
        deps = _agent_dep_warnings(agent, catalog)
        if deps:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "依赖未上架/不可用，禁止上架该 Agent",
                    "deps": deps,
                    "hint": "请先将相关 Skill/MCP/Tool 审核到「已发布」或「已上架」。",
                },
            )
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
    try:
        data = await _core_get("/workspace/agents", params={"limit": 200})
        for a in data.get("agents", []) or []:
            st = a.get("status", "")
            if st in ("published", "listed", "deprecated"):
                items.append({
                    "id": a.get("id", ""),
                    "name": a.get("display_name", "") or a.get("name", ""),
                    "type": "agent",
                    "status": st,
                    "description": (a.get("description", "") or "")[:100],
                })
    except Exception:
        pass  # noqa: intentional — best-effort non-critical operation
    try:
        data = await _core_get("/workspace/skills", params={"limit": 200})
        for s in data.get("skills", []) or []:
            st = s.get("status", "")
            if st in ("published", "listed", "deprecated"):
                items.append({
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "type": "skill",
                    "status": st,
                    "description": (s.get("description", "") or "")[:100],
                })
    except Exception:
        pass  # noqa: intentional — best-effort non-critical operation
    items.sort(key=lambda x: x.get("status", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}
