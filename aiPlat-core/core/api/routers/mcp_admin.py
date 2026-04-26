from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional

import aiohttp
from fastapi import APIRouter, HTTPException, Request

from core.api.deps.rbac import actor_from_http
from core.api.utils.governance import governance_links
from core.governance.audit import audit_event
from core.governance.changeset import record_changeset
from core.governance.gating import autosmoke_enforce, gate_with_change_control
from core.governance.verification import apply_autosmoke_result, mark_resource_pending
from core.harness.kernel.runtime import get_kernel_runtime
from core.mcp.prod_policy import prod_stdio_policy_check, runtime_env
from core.mcp.runtime_sync import sync_mcp_runtime


router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _job_scheduler():
    rt = _rt()
    return getattr(rt, "job_scheduler", None) if rt else None


def _mcp_manager():
    rt = _rt()
    return getattr(rt, "mcp_manager", None) if rt else None


def _workspace_mcp_manager():
    rt = _rt()
    return getattr(rt, "workspace_mcp_manager", None) if rt else None


def _workspace_managers():
    rt = _rt()
    return (
        getattr(rt, "workspace_agent_manager", None) if rt else None,
        getattr(rt, "workspace_skill_manager", None) if rt else None,
        getattr(rt, "workspace_mcp_manager", None) if rt else None,
    )


def _engine_managers():
    rt = _rt()
    return (
        getattr(rt, "agent_manager", None) if rt else None,
        getattr(rt, "skill_manager", None) if rt else None,
        getattr(rt, "mcp_manager", None) if rt else None,
    )


# ---------------------------
# MCP (directory-based config)
# ---------------------------


@router.get("/mcp/servers")
async def list_mcp_servers():
    """List MCP servers configured via filesystem (mcps/<server>/server.yaml)."""
    mgr = _mcp_manager()
    if not mgr:
        return {"servers": []}
    return {
        "servers": [
            {
                "name": s.name,
                "enabled": s.enabled,
                "transport": s.transport,
                "url": s.url,
                "command": s.command,
                "args": s.args,
                "auth": s.auth,
                "allowed_tools": s.allowed_tools,
                "metadata": s.metadata,
            }
            for s in mgr.list_servers()
        ]
    }


@router.post("/mcp/servers/{server_name}/enable")
async def enable_mcp_server(server_name: str):
    """Enable an MCP server in filesystem config."""
    store = _store()
    mgr = _mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="MCP manager not available")

    change_id = None
    if store and autosmoke_enforce(store=store):
        wam, wsm, wmm = _workspace_managers()
        am, sm, mm = _engine_managers()
        change_id = await gate_with_change_control(
            store=store,
            operation="mcp.enable",
            targets=[("mcp", str(server_name))],
            actor={"actor_id": "admin"},
            workspace_agent_manager=wam,
            workspace_skill_manager=wsm,
            skill_manager=sm,
            workspace_mcp_manager=wmm,
            mcp_manager=mm,
        )

    ok = mgr.set_enabled(server_name, True)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")

    if store:
        await record_changeset(
            store=store,
            name="mcp.enable",
            target_type="change",
            target_id=str(change_id or f"chg-{server_name}"),
            status="success",
            args={"targets": [{"type": "mcp", "id": str(server_name)}]},
            user_id="admin",
        )

    # Sync runtime tools best-effort
    await sync_mcp_runtime(mcp_manager=mgr, workspace_mcp_manager=_workspace_mcp_manager())
    return {"status": "enabled", "change_id": change_id, "links": governance_links(change_id=change_id) if change_id else {}}


@router.post("/mcp/servers/{server_name}/disable")
async def disable_mcp_server(server_name: str):
    """Disable an MCP server in filesystem config."""
    mgr = _mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="MCP manager not available")
    ok = mgr.set_enabled(server_name, False)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    await sync_mcp_runtime(mcp_manager=mgr, workspace_mcp_manager=_workspace_mcp_manager())
    return {"status": "disabled"}


# ==================== Workspace MCP servers ====================


@router.get("/workspace/mcp/servers")
async def list_workspace_mcp_servers():
    """List workspace MCP servers (~/.aiplat/mcps)."""
    mgr = _workspace_mcp_manager()
    if not mgr:
        return {"servers": []}
    return {
        "servers": [
            {
                "name": s.name,
                "enabled": s.enabled,
                "transport": s.transport,
                "url": s.url,
                "command": s.command,
                "args": s.args,
                "auth": s.auth,
                "allowed_tools": s.allowed_tools,
                "metadata": s.metadata,
            }
            for s in mgr.list_servers()
        ]
    }


@router.get("/workspace/mcp/servers/{server_name}")
async def get_workspace_mcp_server(server_name: str):
    """Get workspace MCP server details."""
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    s = mgr.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    return {
        "name": s.name,
        "enabled": s.enabled,
        "transport": s.transport,
        "url": s.url,
        "command": s.command,
        "args": s.args,
        "auth": s.auth,
        "allowed_tools": s.allowed_tools,
        "metadata": s.metadata,
    }


@router.get("/workspace/mcp/servers/{server_name}/tools")
async def discover_workspace_mcp_tools(server_name: str, timeout_seconds: int = 10):
    """
    Best-effort tool discovery via MCP protocol (tools/list).
    - For sse/http: POST JSON-RPC to url
    - For stdio: spawn process, send JSON-RPC via stdin/stdout (dev/staging recommended)
    """
    mgr = _workspace_mcp_manager()
    store = _store()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    s = mgr.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")

    transport = str(s.transport or "").strip().lower()
    ok, reason = prod_stdio_policy_check(server_name=server_name, transport=transport, command=s.command, args=s.args, metadata=s.metadata)
    if not ok:
        if store:
            await audit_event(
                store=store,
                kind="mcp_admin",
                name="workspace.mcp.discover_tools",
                status="failed",
                args={"server_name": server_name, "transport": transport, "command": s.command, "args": s.args},
                error=reason,
            )
        raise HTTPException(status_code=403, detail=f"stdio MCP tool discovery is blocked by prod policy: {reason}")

    async def _jsonrpc_post(url: str, payload: dict) -> dict:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=max(1, int(timeout_seconds)))) as session:
            async with session.post(url, data=json.dumps(payload), headers={"Content-Type": "application/json"}) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail=f"MCP server returned HTTP {resp.status}")
                return await resp.json()

    try:
        if transport in {"sse", "http"}:
            if not s.url:
                raise HTTPException(status_code=400, detail="Missing MCP server url")
            # best-effort initialize
            try:
                await _jsonrpc_post(
                    s.url,
                    {
                        "jsonrpc": "2.0",
                        "id": 0,
                        "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "clientInfo": {"name": "aiplat-core", "version": "1.0.0"}},
                    },
                )
            except Exception:
                pass

            res = await _jsonrpc_post(s.url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            if "error" in res and res["error"]:
                raise HTTPException(status_code=502, detail=str(res["error"]))
            tools = (res.get("result") or {}).get("tools") or []
            norm = [{"name": t.get("name"), "description": t.get("description", ""), "input_schema": t.get("inputSchema", {}) or {}} for t in tools if isinstance(t, dict) and t.get("name")]
            if store:
                await audit_event(store=store, kind="mcp_admin", name="workspace.mcp.discover_tools", status="success", args={"server_name": server_name, "transport": transport}, result={"total": len(norm)})
            return {"tools": norm, "total": len(norm)}

        if transport == "stdio":
            if not s.command:
                raise HTTPException(status_code=400, detail="Missing MCP stdio command")
            proc = await asyncio.create_subprocess_exec(s.command, *(s.args or []), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "clientInfo": {"name": "aiplat-core", "version": "1.0.0"}}}
                proc.stdin.write((json.dumps(init) + "\n").encode("utf-8"))  # type: ignore[union-attr]
                await proc.stdin.drain()  # type: ignore[union-attr]
                await asyncio.wait_for(proc.stdout.readline(), timeout=max(1, int(timeout_seconds)))  # type: ignore[union-attr]

                req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))  # type: ignore[union-attr]
                await proc.stdin.drain()  # type: ignore[union-attr]
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=max(1, int(timeout_seconds)))  # type: ignore[union-attr]
                if not line:
                    raise HTTPException(status_code=502, detail="MCP stdio server returned empty response")
                res = json.loads(line.decode("utf-8"))
                if res.get("error"):
                    raise HTTPException(status_code=502, detail=str(res["error"]))
                tools = (res.get("result") or {}).get("tools") or []
                norm = [{"name": t.get("name"), "description": t.get("description", ""), "input_schema": t.get("inputSchema", {}) or {}} for t in tools if isinstance(t, dict) and t.get("name")]
                if store:
                    await audit_event(store=store, kind="mcp_admin", name="workspace.mcp.discover_tools", status="success", args={"server_name": server_name, "transport": transport}, result={"total": len(norm)})
                return {"tools": norm, "total": len(norm)}
            finally:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except Exception:
                    pass

        raise HTTPException(status_code=400, detail=f"Unsupported MCP transport: {transport}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/workspace/mcp/servers/{server_name}/policy-check")
async def check_workspace_mcp_server_policy(server_name: str):
    """Check whether a workspace MCP server can be enabled/discovered under current policy."""
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    s = mgr.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")

    transport = str(s.transport or "").strip().lower()
    ok, reason = prod_stdio_policy_check(server_name=server_name, transport=transport, command=s.command, args=s.args, metadata=s.metadata)

    details: Dict[str, Any] = {"checks": {}, "policy": {}}
    try:
        details["checks"]["metadata_prod_allowed"] = bool((s.metadata or {}).get("prod_allowed", False))
        allowlist_raw = os.environ.get("AIPLAT_PROD_STDIO_MCP_ALLOWLIST", "")
        allowlist = [x.strip() for x in allowlist_raw.split(",") if x.strip()]
        details["checks"]["server_in_allowlist"] = server_name in set(allowlist)
        details["policy"]["AIPLAT_PROD_STDIO_MCP_ALLOWLIST"] = allowlist

        cmd = (s.command or "").strip()
        details["checks"]["command_present"] = bool(cmd)
        details["checks"]["command_absolute"] = bool(cmd.startswith("/"))

        prefixes_raw = os.environ.get("AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES", "")
        parts: List[str] = []
        for chunk in prefixes_raw.split(os.pathsep):
            parts.extend([x.strip() for x in chunk.split(",") if x.strip()])
        details["policy"]["AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES"] = parts
        details["checks"]["command_prefix_ok"] = bool(cmd and any(cmd.startswith((p if p.endswith("/") else p + "/")) or cmd == p for p in parts))

        deny_raw = os.environ.get("AIPLAT_STDIO_DENY_COMMAND_BASENAMES", "bash,sh,zsh")
        deny = [x.strip() for x in deny_raw.split(",") if x.strip()]
        details["policy"]["AIPLAT_STDIO_DENY_COMMAND_BASENAMES"] = deny
        details["checks"]["deny_basename_ok"] = (os.path.basename(cmd).lower() not in {x.lower() for x in deny}) if cmd else True

        details["checks"]["executable_ok"] = bool(cmd and os.path.exists(cmd) and os.access(cmd, os.X_OK))

        a = list(s.args or [])
        max_args = int(os.environ.get("AIPLAT_STDIO_MAX_ARGS", "32") or 32)
        max_len = int(os.environ.get("AIPLAT_STDIO_MAX_ARG_LENGTH", "512") or 512)
        details["policy"]["AIPLAT_STDIO_MAX_ARGS"] = max_args
        details["policy"]["AIPLAT_STDIO_MAX_ARG_LENGTH"] = max_len
        details["checks"]["args_count_ok"] = len(a) <= max_args
        details["checks"]["args_length_ok"] = all(len(str(x)) <= max_len for x in a)

        force_launcher = (os.environ.get("AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD", "") or "").strip().lower() in {"1", "true", "yes", "on"}
        launcher = (os.environ.get("AIPLAT_STDIO_PROD_LAUNCHER") or "").strip()
        details["policy"]["AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD"] = force_launcher
        details["policy"]["AIPLAT_STDIO_PROD_LAUNCHER"] = launcher
        details["checks"]["launcher_required"] = force_launcher
        details["checks"]["launcher_ok"] = (not force_launcher) or (bool(launcher) and cmd == launcher)
    except Exception:
        pass

    return {"env": runtime_env(), "server_name": server_name, "transport": transport, "ok": bool(ok), "reason": reason, "details": details}


@router.post("/workspace/mcp/servers")
async def upsert_workspace_mcp_server(request: dict, http_request: Request):
    """Create or update a workspace MCP server (writes to ~/.aiplat/mcps/<name>/server.yaml + policy.yaml)."""
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    store = _store()
    scheduler = _job_scheduler()
    try:
        from core.management.mcp_manager import MCPServerInfo

        name = str((request or {}).get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Missing required field: name")
        info = MCPServerInfo(
            name=name,
            enabled=bool((request or {}).get("enabled", True)),
            transport=str((request or {}).get("transport") or "sse"),
            url=(request or {}).get("url"),
            command=(request or {}).get("command"),
            args=list((request or {}).get("args") or []),
            auth=(request or {}).get("auth") if isinstance((request or {}).get("auth"), dict) else None,
            allowed_tools=[str(x) for x in ((request or {}).get("allowed_tools") or [])],
            metadata=(request or {}).get("metadata") if isinstance((request or {}).get("metadata"), dict) else {},
        )
        saved = mgr.upsert_server(info)

        if store:
            await audit_event(store=store, kind="mcp_admin", name="workspace.mcp.upsert", status="success", args={"server_name": saved.name, "transport": saved.transport, "command": saved.command, "url": saved.url})

        # Sync runtime tools (best-effort)
        await sync_mcp_runtime(mcp_manager=_mcp_manager(), workspace_mcp_manager=mgr)

        # Mark as pending verification (best-effort)
        try:
            wam, wsm, wmm = _workspace_managers()
            await mark_resource_pending(resource_type="mcp", resource_id=str(saved.name), workspace_agent_manager=wam, workspace_skill_manager=wsm, workspace_mcp_manager=wmm)
        except Exception:
            pass

        # Auto-smoke on MCP upsert (async, dedup)
        try:
            if store is not None and scheduler is not None:
                from core.harness.smoke import enqueue_autosmoke

                actor0 = actor_from_http(http_request, request if isinstance(request, dict) else None)
                tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID") or actor0.get("tenant_id") or "ops_smoke"
                actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID") or actor0.get("actor_id") or "admin"
                sid = str(saved.name)

                wam, wsm, wmm = _workspace_managers()

                async def _on_complete(job_run: Dict[str, Any]):
                    await apply_autosmoke_result(resource_type="mcp", resource_id=sid, job_run=job_run, workspace_agent_manager=wam, workspace_skill_manager=wsm, workspace_mcp_manager=wmm)

                await enqueue_autosmoke(
                    execution_store=store,
                    job_scheduler=scheduler,
                    resource_type="mcp",
                    resource_id=sid,
                    tenant_id=str(tenant_id or "ops_smoke"),
                    actor_id=str(actor_id or "admin"),
                    detail={"op": "upsert", "transport": saved.transport},
                    on_complete=_on_complete,
                )
        except Exception:
            pass
        return {"status": "upserted", "server": {"name": saved.name, "enabled": saved.enabled}}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/workspace/mcp/servers/{server_name}")
async def update_workspace_mcp_server(server_name: str, request: dict, http_request: Request):
    """Update workspace MCP server (upsert semantics)."""
    payload = dict(request or {})
    payload["name"] = server_name
    return await upsert_workspace_mcp_server(payload, http_request)


@router.post("/workspace/mcp/servers/{server_name}/enable")
async def enable_workspace_mcp_server(server_name: str, http_request: Request):
    mgr = _workspace_mcp_manager()
    store = _store()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    actor0 = actor_from_http(http_request, None)
    change_id = None
    # Policy gate: stdio MCP is high risk. Default deny in prod.
    s = mgr.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")

    if store and autosmoke_enforce(store=store):
        wam, wsm, wmm = _workspace_managers()
        am, sm, mm = _engine_managers()
        change_id = await gate_with_change_control(
            store=store,
            operation="workspace.mcp.enable",
            targets=[("mcp", str(server_name))],
            actor=actor0,
            workspace_agent_manager=wam,
            workspace_skill_manager=wsm,
            skill_manager=sm,
            workspace_mcp_manager=wmm,
            mcp_manager=mm,
        )

    ok, reason = prod_stdio_policy_check(server_name=server_name, transport=str(s.transport or ""), command=s.command, args=s.args, metadata=s.metadata)
    if not ok:
        if store:
            await audit_event(store=store, kind="mcp_admin", name="workspace.mcp.enable", status="failed", args={"server_name": server_name, "transport": str(s.transport or ""), "command": s.command, "args": s.args}, error=reason)
        raise HTTPException(status_code=403, detail=f"stdio MCP server is blocked by prod policy: {reason}")
    ok2 = mgr.set_enabled(server_name, True)
    if not ok2:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    if store:
        await audit_event(store=store, kind="mcp_admin", name="workspace.mcp.enable", status="success", args={"server_name": server_name, "transport": str(s.transport or ""), "command": s.command, "args": s.args})
        try:
            await record_changeset(
                store=store,
                name="workspace.mcp.enable",
                target_type="change",
                target_id=str(change_id or f"chg-{server_name}"),
                status="success",
                args={"targets": [{"type": "mcp", "id": str(server_name)}], "transport": str(s.transport or "")},
                user_id=str(actor0.get("actor_id") or "admin"),
                tenant_id=str(actor0.get("tenant_id") or "") or None,
                session_id=str(actor0.get("session_id") or "") or None,
            )
        except Exception:
            pass
    await sync_mcp_runtime(mcp_manager=_mcp_manager(), workspace_mcp_manager=mgr)
    return {"status": "enabled", "change_id": change_id, "links": governance_links(change_id=change_id) if change_id else {}}


@router.post("/workspace/mcp/servers/{server_name}/disable")
async def disable_workspace_mcp_server(server_name: str):
    mgr = _workspace_mcp_manager()
    store = _store()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    ok = mgr.set_enabled(server_name, False)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    if store:
        await audit_event(store=store, kind="mcp_admin", name="workspace.mcp.disable", status="success", args={"server_name": server_name})
    await sync_mcp_runtime(mcp_manager=_mcp_manager(), workspace_mcp_manager=mgr)
    return {"status": "disabled"}

