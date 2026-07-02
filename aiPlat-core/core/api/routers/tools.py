from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Annotated, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from core.api.deps import actor_from_http, rbac_guard
from core.api.utils.run_contract import wrap_execution_result_as_run_summary
from core.api.facades.skill_tool_facade import get_tool_registry
from core.harness.integration import KernelRuntime, get_harness
from core.harness.kernel.runtime import get_kernel_runtime

_logger = logging.getLogger(__name__)
from core.harness.kernel.types import ExecutionRequest
from core.harness.syscalls.llm import sys_llm_generate

router = APIRouter()

_ws_scanned = set()

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


@router.get("/tools", response_model=Dict[str, Any])
async def list_tools(limit: int = 100, offset: int = 0, available_only: bool = False):
    """List all tools"""
    registry = get_tool_registry()
    tools = registry.list_tools()
    # Always try workspace import (registry may be empty at startup)
    try:
        import importlib.util, sys, os
        from core.apps.tools.base import BaseTool, ToolConfig
        tools_dir = os.path.join(os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "tools")
        for f in sorted(os.listdir(tools_dir)):
            if not f.endswith('.py'): continue
            fpath = os.path.join(tools_dir, f)
            if fpath in _ws_scanned: continue
            try:
                mod_name = f"ws_{f[:-3].replace('-','_')}"
                spec = importlib.util.spec_from_file_location(mod_name, fpath)
                if spec is None or spec.loader is None: continue
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                td = getattr(mod, "TOOL_DEF", None)
                if td and isinstance(td, dict):
                    cfg = ToolConfig(name=td.get("name", f[:-3]), description=td.get("description", ""))
                    tool = BaseTool(cfg)
                    tool._execute_fn = td.get("execute")
                    setattr(tool._config, 'metadata', {"provenance": {"scope": "workspace", "tool_path": fpath}})
                    registry.register(tool)
            except Exception:
                _logger.warning("工作空间工具导入失败: %s", fpath, exc_info=True)
            _ws_scanned.add(fpath)
        tools = registry.list_tools()
    except Exception:
        _logger.warning("工作空间工具发现失败", exc_info=True)
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
            info["parameters"] = getattr(tool._config, "parameters", {}) if hasattr(tool, '_config') else {}
        # Workspace tools (from discovery) have provenance metadata with scope
        meta = getattr(tool._config, 'metadata', {}) if hasattr(tool, '_config') else {}
        prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
        if prov.get("scope") == "workspace":
            continue  # workspace tools belong in /workspace/tools, not here
        info["protected"] = True if not prov.get("scope") else False
        info["scope"] = prov.get("scope") or "engine"
        if prov:
            info["provenance"] = {"scope": info["scope"], "tool_path": prov.get("tool_path", ""),
                "source_type": prov.get("source_type", "filesystem"),
                "source": prov.get("source", ""),
                "signature": prov.get("signature", ""),
                "signature_verified": prov.get("signature_verified", False),
                "signature_verified_key_id": prov.get("signature_verified_key_id", "")}
        result.append(info)
    
    return {"total": len(tools), "tools": result}


@router.delete("/tools/{tool_name}", response_model=Dict[str, Any])
async def delete_workspace_tool(tool_name: str, http_request: Request):
    """Delete a workspace tool — removes .py file and unregisters from ToolRegistry."""
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

    # Only workspace tools can be deleted
    meta = getattr(tool._config, 'metadata', {}) if hasattr(tool, '_config') else {}
    prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
    if not prov or prov.get('scope') != 'workspace':
        raise HTTPException(status_code=403, detail="Only workspace tools can be deleted")

    # Remove .py file and companion files
    import os
    tool_path = prov.get('tool_path', '')
    try:
        if tool_path and os.path.exists(tool_path):
            os.remove(tool_path)
        # Also clean up manifest if exists
        manifest_path = tool_path.replace('.py', '.manifest.json') if tool_path else ''
        if manifest_path and os.path.exists(manifest_path):
            os.remove(manifest_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove file: {str(e)}")

    # Unregister from ToolRegistry
    registry.unregister(tool_name)

    return {"status": "deleted", "name": tool_name}


@router.put("/tools/{tool_name}", response_model=Dict[str, Any])
async def update_tool_config(tool_name: str, request: dict):
    """Update tool configuration"""
    raise HTTPException(  # noqa: error-structured
        status_code=403,
        detail="Tools are engine-defined and cannot be edited via API. Use configuration files/feature flags instead.",
    )


@router.post("/tools", response_model=Dict[str, Any])
async def create_workspace_tool(request: dict, http_request: Request, rt: RuntimeDep = None):
    """Create a new workspace tool. Writes a .py file to ~/.aiplat/tools/ and registers it."""
    name = str(request.get("name") or "").strip()
    description = str(request.get("description") or "").strip()
    code = str(request.get("code") or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    if not name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="name must be alphanumeric (underscores and hyphens allowed)")

    # Write to workspace tools directory
    import os
    tools_dir = Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))
    tools_dir.mkdir(parents=True, exist_ok=True)
    tool_file = tools_dir / f"{name}.py"
    if tool_file.exists():
        raise HTTPException(status_code=409, detail=f"Tool '{name}' already exists")

    # Validate Python syntax before saving
    try:
        compile(code, str(tool_file), 'exec')
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Python 语法错误 line {e.lineno}: {e.msg}")

    tool_file.write_text(code, encoding="utf-8")

    # Register the new tool directly into the global registry
    try:
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location(f"aiplat_user_tool_{name.replace('-','_')}", str(tool_file))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"aiplat_user_tool_{name.replace('-','_')}"] = mod
        spec.loader.exec_module(mod)
        tool_def = getattr(mod, "TOOL_DEF", None)
        if tool_def and isinstance(tool_def, dict):
            from core.apps.tools.discovery import _make_discovery_tool
            entry = {"id": tool_def.get("id", name), "name": tool_def.get("name", name),
                     "description": tool_def.get("description", ""),
                     "parameters": tool_def.get("parameters", {}),
                     "execute": tool_def.get("execute"),
                     "module_path": str(tool_file)}
            t = _make_discovery_tool(entry)
            if hasattr(t, '_config'):
                t._config.metadata = getattr(t._config, 'metadata', {}) or {}
                t._config.metadata['provenance'] = {"scope": "workspace", "tool_path": str(tool_file)}
            registry.register(t)
        else:
            # Fallback: use full discovery
            from core.apps.tools.discovery import ToolDiscovery
            ToolDiscovery(Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))).register_all()
    except Exception:
        from core.apps.tools.discovery import ToolDiscovery
        ToolDiscovery(Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))).register_all()

    return {"status": "created", "name": name, "path": str(tool_file)}


@router.post("/tools/auto-fill", response_model=Dict[str, Any])
async def tool_auto_fill(request: dict):
    """AI 生成：根据名称和描述，自动生成 TOOL_DEF 代码。"""
    name = str(request.get("name") or "").strip()
    description = str(request.get("description") or "").strip()
    if not name or not description:
        raise HTTPException(status_code=400, detail="name and description are required")

    try:
        from core.harness.utils.prompt_loader import _async_prompt_resolve
        prompt = await _async_prompt_resolve("tool-auto-fill",
            tool_name=name,
            description=description,
        )
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        from core.harness.utils.prompt_loader import _async_prompt_resolve
        model_name = best_model_for_purpose("tool_creation")
        model = create_selected_adapter(model_name=model_name)
        messages = [
            {"role": "system", "content": await _async_prompt_resolve("tool-auto-fill-system-role")},
            {"role": "user", "content": prompt},
        ]
        resp = await sys_llm_generate(model, messages)
        text = str(resp.content if hasattr(resp, 'content') else resp)
        # Extract code between ```python and ``` if present
        import re
        m = re.search(r"```(?:python)?\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        if not text:
            return {"code": "", "error": "LLM returned empty response"}
        # Soft validation — check syntax but don't block, let user fix before save
        try:
            compile(text, '<tool>', 'exec')
        except SyntaxError as e:
            return {"code": text, "category": "general", "description": description, "parameters": {}, "warning": f"语法可能有误: {e.msg} (line {e.lineno})，请手动修正后保存"}
        # Extract category and parameters from generated code
        import ast
        category = "general"
        parameters = {}
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "TOOL_DEF":
                            if isinstance(node.value, ast.Dict):
                                for i, key in enumerate(node.value.keys):
                                    if isinstance(key, ast.Constant):
                                        if key.value == "parameters" and i < len(node.value.values):
                                            try:
                                                params_val = ast.literal_eval(node.value.values[i])
                                                if isinstance(params_val, dict):
                                                    parameters = params_val
                                            except Exception as e:
                                                logging.debug(str(e), exc_info=True)
                            break
            # Guess category from tool name/description
            text_lower = (name + " " + description).lower()
            if any(k in text_lower for k in ["file", "文件", "read", "write", "读", "写", "edit"]):
                category = "file_ops"
            elif any(k in text_lower for k in ["search", "检索", "searching", "lookup"]):
                category = "retrieval"
            elif any(k in text_lower for k in ["api", "http", "url", "网络", "post", "get"]):
                category = "network"
            elif any(k in text_lower for k in ["db", "sql", "数据库", "query", "mongo"]):
                category = "database"
            elif any(k in text_lower for k in ["code", "代码", "exec", "run", "执行", "compile"]):
                category = "execution"
            elif any(k in text_lower for k in ["data", "数据", "transform", "convert", "format"]):
                category = "data"
            elif any(k in text_lower for k in ["calc", "计算", "math", "数学"]):
                category = "math"
        except SyntaxError:
            pass
        return {"code": text, "category": category, "description": description, "parameters": parameters}
    except Exception as e:
        return {"code": "", "category": "general", "description": description, "parameters": {}, "error": f"Auto-fill failed: {str(e)}"}


@router.post("/tools/{tool_name}/execute", response_model=Dict[str, Any])
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
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return JSONResponse(status_code=200, content=resp)


@router.post("/tools/{tool_name}/sign", response_model=Dict[str, Any])
async def sign_tool(tool_name: str, request: dict, http_request: Request, rt: RuntimeDep = None):
    """
    Sign a workspace tool's .py file with an Ed25519 private key.
    Writes a companion TOOL.manifest.json next to the .py file.

    Body: { "private_key": "-----BEGIN PRIVATE KEY-----..." }

    Only workspace tools (those discovered from ~/.aiplat/tools/) are signable.
    Engine tools are code-defined and protected.
    """
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

    if http_request is not None:
        deny = await rbac_guard(http_request=http_request, payload={}, action="sign", resource_type="tool", resource_id=str(tool_name))
        if deny:
            return deny

    # Find the tool's file path from config metadata
    tool_path = None
    if hasattr(tool, '_config') and hasattr(tool._config, 'metadata'):
        meta = getattr(tool._config, 'metadata', {}) or {}
        prov = meta.get('provenance', {}) if isinstance(meta, dict) else {}
        integrity = meta.get('integrity', {}) if isinstance(meta, dict) else {}
        tool_path = integrity.get('file_path') or prov.get('tool_path')
    if not tool_path:
        raise HTTPException(status_code=400, detail="Tool file path not found — only workspace tools support signing")

    tool_fpath = Path(tool_path)
    if not tool_fpath.exists():
        raise HTTPException(status_code=500, detail=f"Tool file not found: {tool_path}")

    private_key = str(request.get("private_key") or "").strip()
    private_key = private_key.replace("\\n", "\n")  # normalize escaped newlines from frontend
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    try:
        from core.apps.tools.discovery import _sha256_file
        from core.harness.infrastructure.crypto.signature import sign_skill as sign_tool

        bundle_sha256 = _sha256_file(tool_fpath)
        version = request.get("version") or "0.1.0"

        signature = sign_tool(
            private_key=private_key,
            skill_id=tool_name,
            version=str(version),
            bundle_sha256=bundle_sha256,
        )

        # Write companion manifest
        manifest_path = tool_fpath.parent / f"{tool_fpath.stem}.TOOL.manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        manifest["signature"] = signature
        manifest["version"] = str(version)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        # Sync signature into memory so list_tools() reflects the signed state
        if hasattr(tool, '_config') and hasattr(tool._config, 'metadata'):
            meta = getattr(tool._config, 'metadata', {}) or {}
            meta.setdefault('provenance', {})['signature'] = signature

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
