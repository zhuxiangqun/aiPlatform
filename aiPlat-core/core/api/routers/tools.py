from __future__ import annotations

from typing import Any, Annotated, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps.rbac import actor_from_http, rbac_guard
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.apps.tools.base import get_tool_registry
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.kernel.types import ExecutionRequest

router = APIRouter()

RuntimeDep = Annotated[Optional[KernelRuntime], Depends(get_kernel_runtime)]


def _store(rt: Optional[KernelRuntime]):
    return getattr(rt, "execution_store", None) if rt else None


def _inject_http_request_context(payload: Any, http_request: Request, *, entrypoint: str) -> Any:
    """
    Best-effort: inject tenant/actor/request identity from headers into payload.context.
    Used for tenant/actor propagation into harness/syscalls.
    """
    if not isinstance(payload, dict):
        return payload
    try:
        ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        ctx = dict(ctx) if isinstance(ctx, dict) else {}
        ctx.setdefault("entrypoint", str(entrypoint or "api"))

        tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID") or http_request.headers.get("x-aiplat-tenant-id")
        actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or http_request.headers.get("x-aiplat-actor-id")
        actor_role = http_request.headers.get("X-AIPLAT-ACTOR-ROLE") or http_request.headers.get("x-aiplat-actor-role")
        req_id = http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")
        if tenant_id:
            ctx.setdefault("tenant_id", str(tenant_id))
        if actor_id:
            ctx.setdefault("actor_id", str(actor_id))
        if actor_role:
            ctx.setdefault("actor_role", str(actor_role))
        if req_id:
            ctx.setdefault("request_id", str(req_id))
        payload["context"] = ctx
    except Exception:
        return payload
    return payload


async def _audit_execute(
    *,
    http_request: Request,
    payload: Optional[Dict[str, Any]],
    resource_type: str,
    resource_id: str,
    resp: Dict[str, Any],
    rt: Optional[KernelRuntime],
    action: Optional[str] = None,
) -> None:
    """PR-06: enterprise audit for execute entrypoints (best-effort)."""
    store = _store(rt)
    if not store:
        return
    try:
        actor = actor_from_http(http_request, payload)
        await store.add_audit_log(
            action=action or f"execute_{resource_type}",
            status=str(resp.get("legacy_status") or resp.get("status") or ("ok" if resp.get("ok") else "failed")),
            tenant_id=str(actor.get("tenant_id") or "") or None,
            actor_id=str(actor.get("actor_id") or "") or None,
            actor_role=str(actor.get("actor_role") or "") or None,
            resource_type=str(resource_type),
            resource_id=str(resource_id),
            request_id=str(resp.get("request_id") or "") or (http_request.headers.get("X-AIPLAT-REQUEST-ID") or http_request.headers.get("x-aiplat-request-id")),
            run_id=str(resp.get("run_id") or resp.get("execution_id") or "") or None,
            trace_id=str(resp.get("trace_id") or "") or None,
            detail={
                "status": resp.get("status"),
                "legacy_status": resp.get("legacy_status"),
                "error": resp.get("error"),
            },
        )
    except Exception:
        return


@router.get("/tools")
async def list_tools(limit: int = 100, offset: int = 0, available_only: bool = False):
    """List all tools"""
    registry = get_tool_registry()
    tools = registry.list_tools()
    result = []
    for t in tools[offset : offset + limit]:
        tool = registry.get(t)
        info: Dict[str, Any] = {"name": t}
        if tool:
            avail = registry.get_availability(t) if hasattr(registry, "get_availability") else {"available": True, "reason": None}
            info["available"] = bool(avail.get("available"))
            info["unavailable_reason"] = avail.get("reason")
            if available_only and not info["available"]:
                continue
            info["description"] = tool.get_description()
            info["category"] = getattr(tool._config, "category", "general") if hasattr(tool, "_config") else "general"
            # Tools are code-defined engine capabilities; do not edit via UI/API.
            info["protected"] = True
            info["scope"] = "engine"
            stats = tool.get_stats() if hasattr(tool, "get_stats") else None
            if stats:
                info["stats"] = stats
            info["config"] = {}
            if hasattr(tool, "_config"):
                cfg = tool._config
                info["config"] = {
                    "name": cfg.name if hasattr(cfg, "name") else t,
                    "description": cfg.description if hasattr(cfg, "description") else "",
                    "timeout_seconds": cfg.timeout_seconds if hasattr(cfg, "timeout_seconds") else None,
                    "max_concurrent": cfg.max_concurrent if hasattr(cfg, "max_concurrent") else None,
                }
            info["parameters"] = tool._config.parameters if hasattr(tool, "_config") and hasattr(tool._config, "parameters") else {}
            info["status"] = "enabled" if info.get("available", True) else "unavailable"
            info["enabled"] = True
        result.append(info)
    return {"tools": result, "total": len(tools)}


@router.get("/tools/{tool_name}")
async def get_tool(tool_name: str):
    """Get tool details"""
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

    info: Dict[str, Any] = {"name": tool_name}
    info["description"] = tool.get_description()
    if hasattr(registry, "get_availability"):
        avail = registry.get_availability(tool_name)
        info["available"] = bool(avail.get("available"))
        info["unavailable_reason"] = avail.get("reason")
    info["category"] = getattr(tool._config, "category", "general") if hasattr(tool, "_config") else "general"
    info["protected"] = True
    info["scope"] = "engine"

    stats = tool.get_stats() if hasattr(tool, "get_stats") else None
    if stats:
        info["stats"] = stats

    if hasattr(tool, "_config"):
        cfg = tool._config
        info["config"] = {
            "name": cfg.name if hasattr(cfg, "name") else tool_name,
            "description": cfg.description if hasattr(cfg, "description") else "",
            "timeout_seconds": cfg.timeout_seconds if hasattr(cfg, "timeout_seconds") else None,
            "max_concurrent": cfg.max_concurrent if hasattr(cfg, "max_concurrent") else None,
        }

    info["parameters"] = tool._config.parameters if hasattr(tool, "_config") and hasattr(tool._config, "parameters") else {}
    info["status"] = "enabled"
    info["enabled"] = True
    return info


@router.put("/tools/{tool_name}")
async def update_tool_config(tool_name: str, request: dict):
    """Update tool configuration"""
    raise HTTPException(
        status_code=403,
        detail="Tools are engine-defined and cannot be edited via API. Use configuration files/feature flags instead.",
    )


@router.post("/tools/{tool_name}/execute")
async def execute_tool(tool_name: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """Execute a tool with given parameters"""
    harness = get_harness()
    payload = _inject_http_request_context(dict(request or {}), http_request, entrypoint="api")
    deny = await rbac_guard(http_request=http_request, payload=payload, action="execute", resource_type="tool", resource_id=str(tool_name))
    if deny:
        return deny

    ctx0 = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    user_id = payload.get("user_id") or (ctx0.get("actor_id") if isinstance(ctx0, dict) else None) or "system"
    session_id = payload.get("session_id") or (ctx0.get("session_id") if isinstance(ctx0, dict) else None) or "default"
    exec_req = ExecutionRequest(kind="tool", target_id=tool_name, payload=payload, user_id=str(user_id), session_id=str(session_id))
    result = await harness.execute(exec_req)
    resp = wrap_execution_result_as_run_summary(result)
    # Keep legacy behavior: tool execute returns 200 even when failed, but carries {ok:false,error:{...}}.
    try:
        await _audit_execute(http_request=http_request, payload=payload, resource_type="tool", resource_id=str(tool_name), resp=resp, rt=rt)
    except Exception:
        pass
    return JSONResponse(status_code=200, content=resp)

