from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

from pathlib import Path

import aiohttp
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from core.api.deps import actor_from_http
from core.api.utils.governance import governance_links
from core.governance.audit import audit_event
from core.governance.changeset import record_changeset
from core.governance.gating import autosmoke_enforce, gate_with_change_control
from core.governance.verification import apply_autosmoke_result, mark_resource_pending
from core.harness.kernel.runtime import get_kernel_runtime
from core.mcp.prod_policy import prod_stdio_policy_check, runtime_env
from core.mcp.runtime_sync import sync_mcp_runtime


router = APIRouter()

logger = logging.getLogger(__name__)


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
                "status": getattr(s, "status", "draft") or "draft",
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

    # Signature verification best-effort
    server = mgr.get_server(server_name)
    if server and store:
        try:
            from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map
            trusted = await get_trusted_skill_pubkeys_map(store)
            mgr.compute_mcp_signature_verification(server, trusted)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

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


@router.post("/mcp/servers/{server_name}/sign")
async def sign_mcp_server(server_name: str, request: Dict[str, Any]):
    """
    Sign an MCP server directory with an Ed25519 private key.
    Writes MCP.manifest.json alongside server.yaml.

    Body: { "private_key": "-----BEGIN PRIVATE KEY-----..." }
    """
    mgr = _mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="MCP manager not available")

    server = mgr.get_server(server_name)
    if not server:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")

    private_key = str(request.get("private_key") or "").strip()
    private_key = private_key.replace("\\n", "\n")  # normalize escaped newlines from frontend
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    try:
        from core.harness.infrastructure.crypto.signature import sign_skill as sign_mcp

        server_dir = Path(server.metadata.get("filesystem", {}).get("server_dir") or server.metadata.get("provenance", {}).get("server_dir") or "")
        if not server_dir or not server_dir.exists():
            raise HTTPException(status_code=500, detail="MCP server directory not found")

        # Ensure integrity is computed
        mgr._enrich_mcp_provenance_and_integrity(server.metadata, server_dir=server_dir)
        integ = server.metadata.get("integrity", {})
        bundle_sha256 = integ.get("bundle_sha256", "")
        if not bundle_sha256:
            raise HTTPException(status_code=500, detail="Could not compute bundle_sha256")

        version = str(request.get("version") or "0.1.0")

        signature = sign_mcp(
            private_key=private_key,
            skill_id=server_name,
            version=version,
            bundle_sha256=bundle_sha256,
        )

        # Write MCP.manifest.json
        manifest_path = server_dir / "MCP.manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        manifest["signature"] = signature
        manifest["version"] = str(version)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        # Re-enrich to pick up the signature
        mgr._enrich_mcp_provenance_and_integrity(server.metadata, server_dir=server_dir)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signing failed: {str(e)}")

    return {
        "status": "signed",
        "bundle_sha256": bundle_sha256,
        "version": str(version),
        "signature": signature,
    }


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


@router.post("/mcp/servers/reload")
async def reload_mcp_servers():
    """Reload MCP server configs from disk (engine scope)."""
    mgr = _mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="MCP manager not available")
    mgr.reload()
    await sync_mcp_runtime(mcp_manager=mgr, workspace_mcp_manager=_workspace_mcp_manager())
    return {"status": "reloaded", "servers": mgr.get_server_names()}


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
                "status": getattr(s, "status", "draft") or "draft",
                "transport": s.transport,
                "url": s.url,
                "command": s.command,
                "args": s.args,
                "auth": s.auth,
                "allowed_tools": s.allowed_tools,
                "metadata": s.metadata,
                "source": getattr(s, "source", "external") or "external",
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
        "status": getattr(s, "status", "draft") or "draft",
        "transport": s.transport,
        "url": s.url,
        "command": s.command,
        "args": s.args,
        "auth": s.auth,
        "allowed_tools": s.allowed_tools,
        "metadata": s.metadata,
        "source": getattr(s, "source", "external") or "external",
    }


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
    except Exception as e:
        logging.debug(str(e), exc_info=True)

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
            source=str((request or {}).get("source") or ((request or {}).get("metadata") or {}).get("source") or "external"),
        )
        saved = mgr.upsert_server(info)

        # Auto-grant EXECUTE permission for system/admin on newly created MCP servers
        try:
            from core.apps.tools.permission import get_permission_manager, Permission
            pm = get_permission_manager()
            for uid in ("system", "admin"):
                pm.grant_permission(uid, saved.name, Permission.EXECUTE, granted_by="auto_create")
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        if store:
            await audit_event(store=store, kind="mcp_admin", name="workspace.mcp.upsert", status="success", args={"server_name": saved.name, "transport": saved.transport, "command": saved.command, "url": saved.url})

        # Sync runtime tools (best-effort)
        await sync_mcp_runtime(mcp_manager=_mcp_manager(), workspace_mcp_manager=mgr)

        # Mark as pending verification (best-effort)
        try:
            wam, wsm, wmm = _workspace_managers()
            await mark_resource_pending(resource_type="mcp", resource_id=str(saved.name), workspace_agent_manager=wam, workspace_skill_manager=wsm, workspace_mcp_manager=wmm)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

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
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        return {"status": "upserted", "server": {"name": saved.name, "enabled": saved.enabled}}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/workspace/mcp/servers/auto-fill")
async def mcp_auto_fill(request: dict):
    """AI 智能填充：根据名称和描述，自动推荐 MCP 服务器配置。"""
    name = str(request.get("name") or "").strip()
    description = str(request.get("description") or "").strip()
    if not name or not description:
        raise HTTPException(status_code=400, detail="name and description are required")

    try:
        # Build existing MCP catalog for context
        from core.management.mcp_manager import MCPManager as _Mgr
        mgr = _Mgr()
        ws_mgr = _Mgr(scope="workspace")
        all_servers = list(mgr.list_servers() or []) + list(ws_mgr.list_servers() or [])
        mcp_catalog = "\n".join(
            (lambda s: f"  - {s.name}: enabled={getattr(s,'enabled',True)} transport={getattr(s,'transport','')}"
                       + (f" | {str(getattr(s,'metadata',{}).get('description','') or '')[:80]}" if getattr(s,'metadata',{}).get('description','') else "")
                       + (f" | tools: {', '.join(str(t) for t in (getattr(s,'allowed_tools',[]) or [])[:3])}" if getattr(s,'allowed_tools',[]) else ""))(s)
            for s in all_servers
        ) or "(无)"

        from core.harness.utils.prompt_loader import _async_prompt_resolve
        prompt = await _async_prompt_resolve("mcp-auto-fill",
            server_name=name,
            description=description,
            mcp_catalog=mcp_catalog,
        )
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        from core.harness.syscalls.llm import sys_llm_generate
        model_name = best_model_for_purpose("tool_creation")
        model = create_selected_adapter(model_name=model_name)
        from core.harness.utils.prompt_loader import _async_prompt_resolve
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("mcp-auto-fill-system-role")},
            {"role": "user", "content": prompt},
        ]
        resp = await sys_llm_generate(model, messages)
        text = str(resp.content if hasattr(resp, 'content') else resp)

        import re
        m = re.search(r'```(?:json)?\n?(.*?)```', text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        try:
            import json as _json
            config = _json.loads(text)
        except Exception:
            return {"error": "LLM returned non-JSON output", "raw": text[:500]}

        return {
            "transport": config.get("transport", "sse"),
            "url": config.get("url", ""),
            "command": config.get("command", ""),
            "args": config.get("args", []),
            "allowed_tools": config.get("allowed_tools", []),
            "auth": config.get("auth"),
            "metadata": config.get("metadata", {}),
        }
    except Exception as e:
        return {"error": f"Auto-fill failed: {str(e)}"}


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
        except Exception as e:
            logging.debug(str(e), exc_info=True)
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


@router.post("/workspace/mcp/templates/{template}/create")
async def create_mcp_from_template(template: str, data: dict):
    """Create a new MCP server from a seed template, copying config + script files."""
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")

    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    allowed_templates = {"http_bridge", "shell_executor", "file_ops", "db_query"}
    if template not in allowed_templates:
        raise HTTPException(status_code=400, detail=f"Unknown template: {template}")

    info = MCPServerInfo(
        name=name,
        enabled=False,
        transport="stdio",
        command=sys.executable,
        args=["mcp_server.py"],
        metadata={"description": data.get("description", ""), "template": template},
    )
    mgr.upsert_server(info)

    from pathlib import Path as _P
    seeds_root = _P(__file__).resolve().parents[2] / "core" / "workspace_seeds" / "mcps" / template
    server_dir = mgr._resolve_mcp_base_path() / name

    if seeds_root.exists():
        import shutil as _shutil
        for seed_file in seeds_root.iterdir():
            if seed_file.is_file():
                dst = server_dir / seed_file.name
                if not dst.exists():
                    _shutil.copy2(seed_file, dst)

    mgr.reload()
    await sync_mcp_runtime(mcp_manager=_mcp_manager(), workspace_mcp_manager=mgr)
    return {"status": "created", "name": name, "template": template}


@router.delete("/workspace/mcp/servers/{server_name}")
async def delete_workspace_mcp_server(server_name: str):
    """Delete a workspace MCP server config + directory."""
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    if not mgr.get_server(server_name):
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    mgr.delete_server(server_name)
    await sync_mcp_runtime(mcp_manager=_mcp_manager(), workspace_mcp_manager=mgr)
    return {"status": "deleted", "name": server_name}


@router.get("/workspace/mcp/servers/{server_name}/tools")
async def list_mcp_server_tools(server_name: str, timeout_seconds: int = 25):
    """Lightweight tools/list — connect to MCP server and return tool definitions (with inputSchema)."""
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    s = mgr.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    if not getattr(s, "enabled", False):
        raise HTTPException(status_code=400, detail="MCP server is disabled")

    transport = str(s.transport or "").strip().lower()
    tools = []

    if transport == "stdio":
        proc = await asyncio.create_subprocess_exec(
            s.command, *(s.args or []),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "clientInfo": {"name": "aiplat-discover", "version": "1.0.0"},
            }}
            proc.stdin.write((json.dumps(init) + "\n").encode("utf-8"))
            await proc.stdin.drain()
            await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_seconds)
            req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
            await proc.stdin.drain()
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_seconds)
            resp = json.loads(line.decode("utf-8"))
            tools = (resp.get("result") or {}).get("tools") or []
        finally:
            try: proc.terminate(); await asyncio.wait_for(proc.wait(), timeout=2)
            except Exception:
                logger.debug("MCP stdio 进程清理失败", exc_info=True)

    elif transport in {"sse", "http"}:
        if not s.url:
            raise HTTPException(status_code=400, detail="Missing URL for SSE/HTTP server")
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as session:
            init_req = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "clientInfo": {"name": "aiplat-discover", "version": "1.0.0"},
            }}
            async with session.post(s.url, json=init_req) as resp:
                if resp.status != 200: raise HTTPException(status_code=502, detail=f"MCP server returned {resp.status}")
            list_req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            async with session.post(s.url, json=list_req) as resp:
                data = await resp.json()
                tools = (data.get("result") or {}).get("tools") or []
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported transport: {transport}")

    return {"tools": tools, "total": len(tools)}


@router.post("/workspace/mcp/servers/{server_name}/test-invoke")
@router.post("/workspace/mcp/servers/{server_name}/test-invoke")
async def test_invoke_mcp_server(server_name: str, data: dict = None):
    """Test an MCP server — connect, list tools, invoke a tool. Set sync=true for inline result."""
    import uuid

    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    s = mgr.get_server(server_name)
    if not s:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")
    if not getattr(s, "enabled", False):
        raise HTTPException(status_code=400, detail="MCP server is disabled — enable it first before testing")

    transport = str(s.transport or "").strip().lower()
    ok, reason = prod_stdio_policy_check(server_name=server_name, transport=transport, command=s.command, args=s.args, metadata=s.metadata)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)

    run_id = f"mcp-test-{server_name}-{uuid.uuid4().hex[:8]}"
    tool_name = (data.get("tool") or "").strip() if data else ""
    tool_args = (data.get("args") or data.get("arguments") or {}) if data else {}
    sync = bool(data.get("sync", False)) if data else False

    if sync:
        steps = await _run_mcp_test(
            run_id=run_id,
            server_name=server_name,
            transport=transport,
            command=s.command,
            args=s.args,
            url=s.url,
            tool_name=tool_name,
            tool_args=tool_args,
            allowed_tools=s.allowed_tools or [],
        )
        ok_result = all(s.get("status") == "ok" for s in steps if s.get("name") != "connect")
        return {"run_id": run_id, "status": "ok" if ok_result else "partial", "steps": steps}

    asyncio.create_task(_run_mcp_test_async(
        run_id=run_id,
        server_name=server_name,
        transport=transport,
        command=s.command,
        args=s.args,
        url=s.url,
        tool_name=tool_name,
        tool_args=tool_args,
        allowed_tools=s.allowed_tools or [],
    ))

    return {"run_id": run_id, "status": "started"}


async def _run_mcp_test_async(
    *, run_id: str, server_name: str, transport: str,
    command: Optional[str], args: Optional[list],
    url: Optional[str], tool_name: str, tool_args: dict,
    allowed_tools: list,
):
    """Wrapper: sleep 2s so frontend can establish SSE connection, then run test."""
    await asyncio.sleep(2)
    await _run_mcp_test(
        run_id=run_id, server_name=server_name, transport=transport,
        command=command, args=args, url=url,
        tool_name=tool_name, tool_args=tool_args,
        allowed_tools=allowed_tools,
    )


async def _run_mcp_test(
    *, run_id: str, server_name: str, transport: str,
    command: Optional[str], args: Optional[list],
    url: Optional[str], tool_name: str, tool_args: dict,
    allowed_tools: list = None,
) -> list:
    """Run MCP test steps. Returns list of step dicts for sync mode, also publishes to EventBus."""
    steps: list = []
    allowed = set(allowed_tools or [])
    _pub_seq = 0  # sequence counter for unique event IDs

    # ── Emit run_start for SSE done detection ──
    store = None
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        if store:
            await store.append_run_event(
                run_id=run_id,
                event_type="run_start",
                trace_id=None, tenant_id=None,
                payload={"kind": "mcp_test", "server_name": server_name, "status": "running"},
            )
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    async def _pub(name: str, status: str, **kwargs):
        """Publish event to EventBus and persist to SQLite for later SSE replay."""
        nonlocal _pub_seq
        try:
            from core.harness.observation.event_bus import EventBus
            import uuid
            t = time.time()
            _pub_seq += 1
            span_id = f"mcp:{name}"
            event: Dict[str, Any] = {
                "id": f"{run_id}:{name}:{_pub_seq}",
                "kind": "mcp",
                "name": name, "status": status,
                "span_id": span_id,
                "trace_id": f"trace-{uuid.uuid4().hex[:12]}",
                "run_id": run_id, "start_time": t,
                "target_type": server_name, "duration_ms": 0,
            }
            event.update(kwargs)
            # Dual-write: args/result as dict for SQLite persistence, args_json/result_json for live SSE
            if "args_json" in event and "args" not in event:
                try: event["args"] = json.loads(str(event["args_json"]))
                except Exception:
                    logger.debug("MCP 事件 args 解析失败，server=%s", server_name, exc_info=True)
            if "result_json" in event and "result" not in event:
                try: event["result"] = json.loads(str(event["result_json"]))
                except Exception:
                    logger.debug("MCP 事件 result 解析失败，server=%s", server_name, exc_info=True)
            if status in ("ok", "error", "success", "failed") and event.get("duration_ms") == 0:
                event["duration_ms"] = int((t - event["start_time"]) * 1000) if event.get("start_time") else 0
            EventBus.publish(run_id, event)
            # Directly persist to SQLite for SSE Phase 1 replay (don't wait for DLQ worker)
            try:
                if store:
                    await store._insert_event_raw(event)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    async def _step(name: str, status: str, **kwargs):
        """Record a test step (both for sync return and EventBus)."""
        step = {"name": name, "status": status}
        step.update(kwargs)
        steps.append(step)
        await _pub(name, status, **kwargs)

    async def _http_post(url_str: str, payload: dict) -> dict:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(url_str, data=json.dumps(payload), headers={"Content-Type": "application/json"}) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {text[:200]}")
                return json.loads(text)

    stdio_proc = None  # Single persistent process for stdio transport
    try:
        tools = []
        t_start = time.time()

        # Step 1: Connect
        await _step("connect", "running", args_json=json.dumps({"transport": transport}))

        if transport in {"sse", "http"}:
            if not url:
                raise Exception("Missing URL for SSE/HTTP MCP server")
            # initialize
            init_resp = await _http_post(url, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "clientInfo": {"name": "aiplat-test", "version": "1.0.0"}}})
            await _step("connect", "ok", duration_ms=int((time.time() - t_start) * 1000))

            # Step 2: Initialize
            await _step("initialize", "running")
            await _step("initialize", "ok", result_json=json.dumps({"server": init_resp.get("result", {}).get("serverInfo", {})}))

            # Step 3: List tools
            await _step("list_tools", "running")
            tools_resp = await _http_post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            tools = (tools_resp.get("result") or {}).get("tools") or []

        elif transport == "stdio":
            # Use same Python binary as the server for cross-venv consistency
            cmd = sys.executable if command == "python3" else command
            stdio_proc = await asyncio.create_subprocess_exec(cmd, *(args or []), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

            # Initialize
            init = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "clientInfo": {"name": "aiplat-test", "version": "1.0.0"}}}
            stdio_proc.stdin.write((json.dumps(init) + "\n").encode("utf-8"))
            await stdio_proc.stdin.drain()
            line = await asyncio.wait_for(stdio_proc.stdout.readline(), timeout=15)
            if not line:
                raise Exception("MCP server closed connection during initialize")
            init_data = json.loads(line.decode("utf-8"))
            if init_data.get("error"):
                raise Exception(f"MCP initialize failed: {init_data['error']}")
            if not init_data.get("result"):
                raise Exception("MCP initialize returned empty result")

            await _step("connect", "ok", duration_ms=int((time.time() - t_start) * 1000))

            await _step("initialize", "running")
            await _step("initialize", "ok", result_json=json.dumps({"server": init_data.get("result", {}).get("serverInfo", {})}))

            # Step 3: List tools
            await _step("list_tools", "running")
            req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            stdio_proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
            await stdio_proc.stdin.drain()
            line = await asyncio.wait_for(stdio_proc.stdout.readline(), timeout=15)
            if not line:
                raise Exception("MCP server closed connection during tools/list")
            tools_resp = json.loads(line.decode("utf-8"))
            tools = (tools_resp.get("result") or {}).get("tools") or []
        else:
            raise Exception(f"Unsupported transport: {transport}")

        # Filter tools by allowed_tools whitelist if configured
        if allowed and tools:
            tools = [t for t in tools if t.get("name") in allowed]
        await _step("list_tools", "ok", result_json=json.dumps({"count": len(tools), "tools": [t.get("name") for t in tools[:10]]}))

        # Step 4: Invoke first allowed tool (or user-specified)
        invoke_name = tool_name or (tools[0].get("name", "") if tools else "")
        if not invoke_name:
            await _step("invoke", "ok", result_json=json.dumps({"message": "No tools to invoke"}))
        else:
            await _step("invoke", "running", args_json=json.dumps({"tool": invoke_name, "args": tool_args}), input_tokens=0, output_tokens=0, cost=0.0)
            t_invoke = time.time()

            if transport in {"sse", "http"}:
                call_resp = await _http_post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": invoke_name, "arguments": tool_args}})
            elif transport == "stdio":
                req = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": invoke_name, "arguments": tool_args}}
                stdio_proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
                await stdio_proc.stdin.drain()
                line = await asyncio.wait_for(stdio_proc.stdout.readline(), timeout=15)
                if not line:
                    raise Exception("MCP server closed connection during tools/call")
                call_resp = json.loads(line.decode("utf-8"))

            error = call_resp.get("error", {})
            result = call_resp.get("result", {})
            dur_ms = int((time.time() - t_invoke) * 1000)
            if error:
                await _step("invoke", "error", duration_ms=dur_ms, error=str(error), input_tokens=0, output_tokens=0, cost=0.0)
            else:
                content = str(result.get("content", json.dumps(result)))
                await _step("invoke", "ok", duration_ms=dur_ms, result_json=json.dumps({"output": content[:5000]}), input_tokens=0, output_tokens=0, cost=0.0)

        # Done
        await _step("finish", "ok", tools_count=len(tools), invoked=invoke_name, result_json=json.dumps({"tools_count": len(tools), "invoked": invoke_name}))

    except Exception as e:
        try:
            await _step("finish", "error", error=str(e))
        except Exception:
            steps.append({"name": "finish", "status": "error", "error": str(e)})
    finally:
        if stdio_proc:
            # Close stdin to signal EOF to the server
            try:
                if stdio_proc.stdin:
                    stdio_proc.stdin.close()
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            # Read stderr for diagnostics
            try:
                if stdio_proc.stderr:
                    stderr_bytes = await asyncio.wait_for(stdio_proc.stderr.read(), timeout=3)
                    if stderr_bytes:
                        logger.error("MCP server '%s' stderr:\n%s", server_name, stderr_bytes.decode("utf-8", errors="replace")[:2000])
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            try:
                stdio_proc.terminate()
                await asyncio.wait_for(stdio_proc.wait(), timeout=2)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

    # ── Emit run_end for SSE done detection ──
    try:
        from core.services.execution_store import get_execution_store
        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        if store:
            final_status = "ok"
            if steps and steps[-1].get("status") == "error":
                final_status = "error"
            await store.append_run_event(
                run_id=run_id,
                event_type="run_end",
                trace_id=None, tenant_id=None,
                payload={"kind": "mcp_test", "server_name": server_name, "status": final_status},
            )
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return steps


@router.post("/workspace/mcp/servers/reload")
async def reload_workspace_mcp_servers():
    """Reload MCP server configs from disk (workspace scope)."""
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    mgr.reload()
    await sync_mcp_runtime(mcp_manager=_mcp_manager(), workspace_mcp_manager=mgr)
    return {"status": "reloaded", "servers": mgr.get_server_names()}


# ── MCP Installer endpoints (workspace scope) ──────────────────────

@router.post("/workspace/mcps/installer/plan")
async def workspace_mcps_installer_plan(request: dict, rt: RuntimeDep = None):
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    try:
        return await mgr.installer_plan(
            source_type=str(request.get("source_type", "")),
            url=request.get("url"),
            ref=request.get("ref"),
            path=request.get("path"),
            mcp_id=request.get("mcp_id"),
            subdir=request.get("subdir"),
            auto_detect_subdir=bool(request.get("auto_detect_subdir", True)),
            metadata=request.get("metadata"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/workspace/mcps/installer/install")
async def workspace_mcps_installer_install(request: dict, rt: RuntimeDep = None):
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    try:
        return await mgr.installer_install(
            source_type=str(request.get("source_type", "")),
            url=request.get("url"),
            ref=request.get("ref"),
            path=request.get("path"),
            mcp_id=request.get("mcp_id"),
            subdir=request.get("subdir"),
            auto_detect_subdir=bool(request.get("auto_detect_subdir", True)),
            allow_overwrite=bool(request.get("allow_overwrite", False)),
            metadata=request.get("metadata"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/workspace/mcps/installer/resolve-head")
async def workspace_mcps_installer_resolve_head(request: dict, rt: RuntimeDep = None):
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    try:
        return await mgr.installer_resolve_head(url=str(request.get("url", "")))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workspace/mcps/installer/upload-plan")
async def workspace_mcps_installer_upload_plan(
    file: UploadFile = File(...),
    subdir: str = Form(""),
    auto_detect_subdir: str = Form("true"),
    rt: RuntimeDep = None,
):
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        plan = await mgr.installer_plan(
            source_type="zip", path=tmp_path, subdir=subdir or None,
            auto_detect_subdir=auto_detect_subdir.lower() in ("true", "1", "yes"),
        )
        return {"status": "ok", **plan}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"upload_plan_failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/workspace/mcps/installer/upload-install")
async def workspace_mcps_installer_upload_install(
    file: UploadFile = File(...),
    subdir: str = Form(""),
    auto_detect_subdir: str = Form("true"),
    allow_overwrite: str = Form("false"),
    plan_id: str = Form(""),
    rt: RuntimeDep = None,
):
    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        result = await mgr.installer_install(
            source_type="zip", path=tmp_path, subdir=subdir or None,
            auto_detect_subdir=auto_detect_subdir.lower() in ("true", "1", "yes"),
            allow_overwrite=allow_overwrite.lower() in ("true", "1", "yes"),
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"upload_install_failed: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/workspace/mcp/servers/{server_name}/submit-for-review")
async def submit_mcp_for_review(server_name: str):
    """提交 MCP 服务器进入审批流水线。"""
    import time as _time
    from pathlib import Path as _Path

    mgr = _workspace_mcp_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Workspace MCP manager not available")

    servers = mgr.list_servers() or []
    srv = next((s for s in servers if s.name == server_name), None)
    if not srv:
        raise HTTPException(status_code=404, detail=f"MCP server {server_name} not found")

    lint_errors = 0
    lint_warnings = 0
    lint_messages = []

    home = _Path.home() / ".aiplat" / "mcps" / server_name / "server.yaml"
    if home.exists():
        try:
            from core.management.mcp_config_validator import validate_mcp_server
            issues = validate_mcp_server(home)
            for iss in issues:
                lint_messages.append(f"{'ERROR' if iss.severity == 'error' else 'WARN'}: {iss.message}")
                if iss.severity == "error":
                    lint_errors += 1
                else:
                    lint_warnings += 1
        except Exception as e:
            lint_messages.append(f"Validate failed: {e}")
            lint_errors += 1

    lint_result = {
        "risk_level": "high" if lint_errors > 0 else "low",
        "blocked": lint_errors > 0,
        "error_count": lint_errors,
        "warning_count": lint_warnings,
        "messages": lint_messages,
    }

    if lint_errors > 0:
        try:
            info = MCPServerInfo(
                name=server_name,
                enabled=getattr(srv, "enabled", True),
                status=getattr(srv, "status", "draft"),
                transport=srv.transport,
                command=srv.command,
                args=srv.args,
                metadata={"governance": {"status": "failed", "lint_result": lint_result, "submitted_at": _time.time(), "last_op": "submit_for_review"}},
            )
            mgr.upsert_server(info)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        raise HTTPException(status_code=422, detail={"message": f"配置校验未通过：{lint_errors} 个错误", "lint": lint_result})

    try:
        meta = dict(getattr(srv, "metadata", {}) or {})
        meta["governance"] = {"status": "pending", "lint_result": lint_result, "submitted_at": _time.time(), "last_op": "submit_for_review"}
        info = MCPServerInfo(
            name=server_name,
            enabled=True,
            status="ready",
            transport=srv.transport,
            command=srv.command,
            args=srv.args,
            url=srv.url,
            auth=srv.auth,
            allowed_tools=srv.allowed_tools,
            metadata=meta,
        )
        mgr.upsert_server(info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update MCP server: {e}")

    return {
        "status": "ok",
        "server_name": server_name,
        "new_status": "ready",
        "governance": "pending",
        "lint": {"risk_level": lint_result["risk_level"], "error_count": lint_errors, "warning_count": lint_warnings},
    }


@router.get("/mcp/servers/seeds")
async def list_mcp_seeds():
    """List available MCP server seed templates from workspace_seeds/mcps/."""
    import yaml as _yaml

    seeds_dir = Path(__file__).resolve().parents[3] / "core" / "workspace_seeds" / "mcps"
    if not seeds_dir.exists():
        return {"seeds": [], "total": 0}

    seeds = []
    for item in sorted(seeds_dir.iterdir()):
        if not item.is_dir():
            continue
        server_yaml = item / "server.yaml"
        if not server_yaml.exists():
            continue
        try:
            data = _yaml.safe_load(server_yaml.read_text(encoding="utf-8")) or {}
            installed = (Path.home() / ".aiplat" / "mcps" / item.name).exists()
            seeds.append({
                "id": item.name,
                "name": str(data.get("name") or item.name),
                "transport": str(data.get("transport") or "sse"),
                "description": str(data.get("metadata", {}).get("description", "")),
                "installed": installed,
            })
        except Exception:
            continue
    return {"seeds": seeds, "total": len(seeds)}


@router.post("/mcp/servers/seeds/{seed_id}/install")
async def install_mcp_seed(seed_id: str):
    """Install an MCP server seed template into ~/.aiplat/mcps/."""
    import shutil as _shutil

    seeds_dir = Path(__file__).resolve().parents[3] / "core" / "workspace_seeds" / "mcps"
    seed_dir = seeds_dir / seed_id
    if not seed_dir.exists():
        raise HTTPException(status_code=404, detail=f"Seed template '{seed_id}' not found")

    workspace_dir = Path.home() / ".aiplat" / "mcps"
    dst = workspace_dir / seed_id
    if dst.exists():
        raise HTTPException(status_code=409, detail=f"MCP server '{seed_id}' already installed")

    try:
        workspace_dir.mkdir(parents=True, exist_ok=True)
        _shutil.copytree(seed_dir, dst)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to install seed: {str(e)}")

    # Reload workspace MCP manager
    mgr = _workspace_mcp_manager()
    if mgr and hasattr(mgr, 'reload'):
        try:
            mgr.reload()
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    return {"status": "installed", "id": seed_id}
