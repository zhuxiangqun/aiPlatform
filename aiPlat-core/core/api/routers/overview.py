"""
System Overview endpoint — aggregates system state by architecture layer.

Returns four-layer structure:
  infra    — models, services, servers
  core     — agents, skills, tools, mcp, pipeline
  platform — gateway, users, tenants, knowledge_base
  app      — channels, sessions, apps
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter

router = APIRouter()


@router.get("/overview")
async def system_overview() -> Dict[str, Any]:
    u"""Aggregated system state organized by architecture layer."""
    result: Dict[str, Any] = {"infra": {}, "core": {}, "platform": {}, "app": {}}

    # ─────────────────────────────────────────────────────────────
    # INFRA — Layer 0: Infrastructure
    # ─────────────────────────────────────────────────────────────
    infra: Dict[str, Any] = {"status": "healthy", "models": {}, "servers": {}}

    # Models
    try:
        from core.harness.infrastructure.infra_bridge import ModelManager
        models = ModelManager.list_models()
        available = [m for m in models if m.get("status") not in ("unreachable", "error")]
        infra["models"] = {
            "total": len(models),
            "available": len(available),
            "types": {"chat": sum(1 for m in models if m.get("type") == "chat"),
                       "embedding": sum(1 for m in models if m.get("type") == "embedding")},
        }
    except Exception:
        infra["models"] = {"total": 0, "available": 0, "error": "unavailable"}

    # Servers (port liveness)
    ports = {"management": 8000, "infra": 8001, "core": 8002, "platform": 8003, "app": 8004}
    servers_status: Dict[str, str] = {}
    import socket
    for name, port in ports.items():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
            s.close()
            servers_status[name] = "up"
        except Exception:
            servers_status[name] = "down"
    infra["servers"] = servers_status
    up_count = sum(1 for v in servers_status.values() if v == "up")
    infra["status"] = "healthy" if up_count == len(ports) else "degraded" if up_count >= 3 else "unhealthy"

    result["infra"] = infra

    # ─────────────────────────────────────────────────────────────
    # CORE — Layer 1: AI Platform
    # ─────────────────────────────────────────────────────────────
    core: Dict[str, Any] = {"status": "healthy", "agents": {}, "skills": {}, "tools": 0,
                              "mcp_servers": 0, "pipeline": {}}

    # Agents
    try:
        engine_count = 0
        from core.harness.kernel.runtime import get_kernel_runtime
        rt = get_kernel_runtime()
        if hasattr(rt, "agent_registry") and rt.agent_registry:
            engine_count = len(rt.agent_registry.list_ids() or [])
        workspace_count = 0
        mgr = getattr(rt, "workspace_agent_manager", None) if rt else None
        if mgr:
            workspace_count = mgr.get_agent_count().get("total", 0)
        core["agents"] = {"engine": engine_count, "workspace": workspace_count, "total": engine_count + workspace_count}
    except Exception:
        core["agents"] = {"total": 0, "error": "unavailable"}

    # Skills
    try:
        from core.harness.knowledge.capability_graph import build_capability_graph
        cg = build_capability_graph()
        skill_count = sum(1 for n in cg.nodes.values() if n["type"] == "skill")
        tool_count = sum(1 for n in cg.nodes.values() if n["type"] == "tool")
        mcp_count = sum(1 for n in cg.nodes.values() if n["type"] == "mcp_server")
        core["skills"]["total"] = skill_count
        core["tools"] = tool_count
        core["mcp_servers"] = mcp_count
    except Exception:
        core["skills"]["total"] = 0
        core["tools"] = 0
        core["mcp_servers"] = 0

    # Pipeline
    try:
        if rt and hasattr(rt, "execution_store") and rt.execution_store:
            store = rt.execution_store
            active = len(getattr(store, "_active", {}) or {})
            core["pipeline"] = {"active": active}
    except Exception:
        core["pipeline"] = {"active": 0}

    result["core"] = core

    # ─────────────────────────────────────────────────────────────
    # PLATFORM — Layer 2: Platform Services
    # ─────────────────────────────────────────────────────────────
    platform: Dict[str, Any] = {"status": "healthy", "gateway": {}, "auth": {}, "tenant": {}, "knowledge_base": {}}

    # Gateway routes
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            try:
                r = await client.get("http://localhost:8003/platform/gateway/routes")
                data = r.json() if r.status_code == 200 else {}
                platform["gateway"] = {"routes": len(data.get("routes", []) or [])}
            except Exception:
                platform["gateway"] = {"routes": 0, "error": "unreachable"}
            try:
                r = await client.get("http://localhost:8003/platform/auth/users")
                data = r.json() if r.status_code == 200 else {}
                platform["auth"] = {"users": len(data.get("users", []) or [])}
            except Exception:
                platform["auth"] = {"users": 0, "error": "unreachable"}
            try:
                r = await client.get("http://localhost:8003/platform/tenants")
                data = r.json() if r.status_code == 200 else {}
                platform["tenant"] = {"tenants": len(data.get("tenants", []) or [])}
            except Exception:
                platform["tenant"] = {"tenants": 0, "error": "unreachable"}
            try:
                r = await client.get("http://localhost:8003/platform/kb/collections")
                data = r.json() if r.status_code == 200 else {}
                cols = len(data.get("collections", []) or [])
                platform["knowledge_base"] = {"collections": cols}
            except Exception:
                platform["knowledge_base"] = {"collections": 0, "error": "unreachable"}
    except Exception:
        platform["status"] = "degraded"
        platform["gateway"] = {"error": "unavailable"}
        platform["auth"] = {"error": "unavailable"}
        platform["tenant"] = {"error": "unavailable"}
        platform["knowledge_base"] = {"error": "unavailable"}

    result["platform"] = platform

    # ─────────────────────────────────────────────────────────────
    # APP — Layer 3: Applications
    # ─────────────────────────────────────────────────────────────
    app_layer: Dict[str, Any] = {"status": "healthy", "channels": {}, "sessions": {}, "apps": {}}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            try:
                r = await client.get("http://localhost:8004/app/channels")
                data = r.json() if r.status_code == 200 else {}
                app_layer["channels"] = {"count": len(data.get("channels", []) or [])}
            except Exception:
                app_layer["channels"] = {"count": 0, "error": "unreachable"}
            try:
                r = await client.get("http://localhost:8004/app/sessions")
                data = r.json() if r.status_code == 200 else {}
                sessions = data.get("sessions", []) or []
                active = sum(1 for s in sessions if isinstance(s, dict) and s.get("status") == "active")
                app_layer["sessions"] = {"active": active, "total": len(sessions)}
            except Exception:
                app_layer["sessions"] = {"active": 0, "total": 0, "error": "unreachable"}
            try:
                r = await client.get("http://localhost:8004/app/apps")
                data = r.json() if r.status_code == 200 else {}
                app_layer["apps"] = {"count": len(data.get("apps", []) or [])}
            except Exception:
                app_layer["apps"] = {"count": 0, "error": "unreachable"}
    except Exception:
        app_layer["status"] = "degraded"
        app_layer["channels"] = {"error": "unavailable"}
        app_layer["sessions"] = {"error": "unavailable"}
        app_layer["apps"] = {"error": "unavailable"}

    result["app"] = app_layer

    return result
