"""Workspace Tools API — CRUD for user-defined workspace tools.

Follows the same pattern as workspace_skills.py / workspace_agents.py.
Routes are prefixed with /workspace/tools (registered in server.py).
"""

from __future__ import annotations
import logging

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _read_manifest_provenance(tool_path: str) -> Dict[str, Any]:
    """Read provenance from TOOL.manifest.json if it exists."""
    manifest_path = tool_path.replace('.py', '.TOOL.manifest.json')
    if not os.path.exists(manifest_path):
        return {}
    try:
        data = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
        return data.get('provenance', {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_manifest_provenance(tool_path: str, provenance: Dict[str, Any]) -> None:
    """Write provenance into TOOL.manifest.json, preserving other fields."""
    manifest_path = tool_path.replace('.py', '.TOOL.manifest.json')
    manifest: Dict[str, Any] = {}
    if os.path.exists(manifest_path):
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    # Nested provenance (authoritative) + root-level fields for backward compat
    manifest['provenance'] = provenance
    manifest['signature'] = provenance.get('signature', manifest.get('signature', ''))
    manifest['signature_verified'] = provenance.get('signature_verified', manifest.get('signature_verified', False))
    manifest['signature_key_id'] = provenance.get('signature_key_id', manifest.get('signature_key_id', ''))
    manifest['scope'] = provenance.get('scope', 'workspace')
    manifest['tool_path'] = provenance.get('tool_path', tool_path)
    try:
        Path(manifest_path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        logging.debug(str(e), exc_info=True)


def _scan_workspace_tools() -> List[Dict[str, Any]]:
    """Scan ~/.aiplat/tools/ and return workspace tool summaries."""
    try:
        from core.apps.tools.base import get_tool_registry
        registry = get_tool_registry()
        all_tools = registry.list_tools()
        result = []
        for name in all_tools:
            tool = registry.get(name)
            if tool is None:
                continue
            meta = getattr(tool._config, 'metadata', {}) or {}
            prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
            if prov.get('scope') != 'workspace':
                continue
            entry = {
                "name": name,
                "description": tool.get_description() if hasattr(tool, 'get_description') else "",
                "category": getattr(tool._config, 'category', 'general') if hasattr(tool, '_config') else 'general',
                "parameters": getattr(tool._config, 'parameters', {}) if hasattr(tool, '_config') else {},
                "scope": "workspace",
                "available": True,
                "provenance": prov,
            }
            result.append(entry)
        return result
    except Exception:
        return []


@router.get("/workspace/tools", response_model=Dict[str, Any])
async def list_workspace_tools():
    """List workspace-scoped tools only."""
    tools = _scan_workspace_tools()
    return {"tools": tools, "total": len(tools)}


@router.post("/workspace/tools", response_model=Dict[str, Any])
async def create_workspace_tool(request: dict, http_request: Request):
    """Create a new workspace tool."""
    name = str(request.get("name") or "").strip()
    description = str(request.get("description") or "").strip()
    code = str(request.get("code") or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    if not name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="name must be alphanumeric (underscores and hyphens allowed)")

    tools_dir = Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))
    tools_dir.mkdir(parents=True, exist_ok=True)
    tool_file = tools_dir / f"{name}.py"
    if tool_file.exists():
        raise HTTPException(status_code=409, detail=f"Tool '{name}' already exists")

    try:
        compile(code, str(tool_file), 'exec')
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Python syntax error line {e.lineno}: {e.msg}")

    tool_file.write_text(code, encoding="utf-8")

    try:
        import importlib.util, sys
        from core.apps.tools.base import BaseTool, ToolConfig, get_tool_registry
        mod_name = f"ws_create_{name.replace('-','_')}"
        spec = importlib.util.spec_from_file_location(mod_name, str(tool_file))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            td = getattr(mod, "TOOL_DEF", None)
            if td and isinstance(td, dict):
                cfg = ToolConfig(name=td.get("name", name), description=td.get("description", description), parameters=td.get("parameters", {}))
                tool = BaseTool(cfg)
                tool._execute_fn = td.get("execute")
                setattr(tool._config, 'metadata', {"provenance": {"scope": "workspace", "tool_path": str(tool_file)}})
                get_tool_registry().register(tool)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # Auto-grant EXECUTE permission for system/admin on newly created workspace tools
    try:
        from core.apps.tools.permission import get_permission_manager, Permission
        pm = get_permission_manager()
        for uid in ("system", "admin"):
            pm.grant_permission(uid, name, Permission.EXECUTE, granted_by="auto_create")
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return {"status": "created", "name": name, "path": str(tool_file)}


@router.delete("/workspace/tools/{tool_name}", response_model=Dict[str, Any])
async def delete_workspace_tool(tool_name: str):
    """Delete a workspace tool (hard) — removes .py file and unregisters."""
    from core.apps.tools.base import get_tool_registry
    registry = get_tool_registry()
    tool = registry.get(tool_name)

    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    meta = getattr(tool._config, 'metadata', {}) if hasattr(tool, '_config') else {}
    prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
    if not prov or prov.get('scope') != 'workspace':
        raise HTTPException(status_code=403, detail="Only workspace tools can be deleted")

    tool_path = prov.get('tool_path', '')
    try:
        if tool_path and os.path.exists(tool_path):
            os.remove(tool_path)
        manifest_path = tool_path.replace('.py', '.manifest.json') if tool_path else ''
        if manifest_path and os.path.exists(manifest_path):
            os.remove(manifest_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove file: {str(e)}")

    registry.unregister(tool_name)
    return {"status": "deleted", "name": tool_name}


@router.post("/workspace/tools/{tool_name}/sign", response_model=Dict[str, Any])
async def sign_workspace_tool(tool_name: str, request: dict):
    """Sign a workspace tool with an Ed25519 private key."""
    private_key = str(request.get("private_key") or "").strip().replace("\\n", "\n")
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    from core.harness.infrastructure.crypto.signature import sign_skill, parse_ed25519_private_key
    from core.apps.tools.base import get_tool_registry

    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    meta = getattr(tool._config, 'metadata', {}) if hasattr(tool, '_config') else {}
    prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
    if not prov or prov.get('scope') != 'workspace':
        raise HTTPException(status_code=403, detail="Only workspace tools can be signed")

    tool_path = prov.get('tool_path', '')
    if not tool_path or not os.path.exists(tool_path):
        raise HTTPException(status_code=404, detail="Tool file not found")

    try:
        from core.harness.infrastructure.crypto.signature import sign_skill as _sign_fn
        import hashlib

        bundle_sha256 = hashlib.sha256(Path(tool_path).read_bytes()).hexdigest()
        version = request.get("version") or "0.1.0"

        sig = _sign_fn(
            private_key=private_key,
            skill_id=tool_name,
            version=str(version),
            bundle_sha256=bundle_sha256,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Signing failed: {str(e)}")

    prov['signature'] = sig
    prov['signature_verified'] = False
    prov['signature_key_id'] = version
    meta['provenance'] = prov
    setattr(tool._config, 'metadata', meta)

    _write_manifest_provenance(tool_path, prov)

    return {"status": "signed", "name": tool_name, "signature": sig}


@router.post("/workspace/tools/discover", response_model=Dict[str, Any])
async def discover_workspace_tools():
    """Scan ~/.aiplat/tools/ and return available tool definitions (no subprocess)."""
    import importlib.util, sys
    tools_dir = Path(os.getenv("AIPLAT_TOOLS_PATH", os.path.expanduser("~/.aiplat/tools")))
    results = []
    if not tools_dir.is_dir():
        return {"tools": results, "total": 0}

    for fpath in sorted(tools_dir.glob("*.py")):
        try:
            mod_name = f"discover_{fpath.stem.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(mod_name, str(fpath))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            td = getattr(mod, "TOOL_DEF", None)
            if td and isinstance(td, dict):
                results.append({
                    "name": td.get("name", fpath.stem),
                    "description": td.get("description", ""),
                    "has_parameters": bool(td.get("parameters", {}).get("properties")),
                    "parameters": td.get("parameters", {}),
                })
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    return {"tools": results, "total": len(results)}


@router.put("/workspace/tools/{tool_name}", response_model=Dict[str, Any])
async def update_workspace_tool(tool_name: str, request: dict):
    """Update workspace tool metadata (description, category)."""
    from core.apps.tools.base import get_tool_registry
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    meta = getattr(tool._config, 'metadata', {}) if hasattr(tool, '_config') else {}
    prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
    if not prov or prov.get('scope') != 'workspace':
        raise HTTPException(status_code=403, detail="Only workspace tools can be updated")

    description = request.get('description')
    category = request.get('category')

    if description is not None and hasattr(tool._config, 'description'):
        setattr(tool._config, 'description', description)
    if category is not None and hasattr(tool._config, 'category'):
        setattr(tool._config, 'category', category)

    tool_path = prov.get('tool_path', '')
    if tool_path and os.path.exists(tool_path):
        try:
            content = Path(tool_path).read_text(encoding='utf-8')
            if description is not None:
                import re
                content = re.sub(
                    r'("description"\s*:\s*)"[^"]*"',
                    f'\\1"{description}"',
                    content
                )
            Path(tool_path).write_text(content, encoding='utf-8')
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    return {"status": "updated", "name": tool_name}


@router.get("/workspace/tools/{tool_name}/source", response_model=Dict[str, Any])
async def get_workspace_tool_source(tool_name: str):
    """Return the .py source file content for a workspace tool."""
    from core.apps.tools.base import get_tool_registry
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    meta = getattr(tool._config, 'metadata', {}) if hasattr(tool, '_config') else {}
    prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
    if not prov or prov.get('scope') != 'workspace':
        raise HTTPException(status_code=403, detail="Only workspace tools support source retrieval")

    tool_path = prov.get('tool_path', '')
    if not tool_path or not os.path.exists(tool_path):
        raise HTTPException(status_code=404, detail="Tool file not found on disk")

    try:
        content = Path(tool_path).read_text(encoding='utf-8')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read source: {str(e)}")

    return {
        "name": tool_name,
        "path": tool_path,
        "source": content,
        "description": tool.get_description() if hasattr(tool, 'get_description') else "",
        "category": getattr(tool._config, 'category', 'general') if hasattr(tool, '_config') else 'general',
    }


@router.put("/workspace/tools/{tool_name}/source", response_model=Dict[str, Any])
async def update_workspace_tool_source(tool_name: str, request: dict):
    """Save Python source code for a workspace tool. Validates syntax before saving."""
    from core.apps.tools.base import get_tool_registry, BaseTool, ToolConfig
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    meta = getattr(tool._config, 'metadata', {}) if hasattr(tool, '_config') else {}
    prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
    if not prov or prov.get('scope') != 'workspace':
        raise HTTPException(status_code=403, detail="Only workspace tools can be updated")

    source = str(request.get("source", "") or "")
    if not source.strip():
        raise HTTPException(status_code=400, detail="source is required")

    tool_path = prov.get('tool_path', '')
    if not tool_path:
        raise HTTPException(status_code=404, detail="Tool file path not found")

    # Validate Python syntax
    try:
        compile(source, tool_path, 'exec')
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Python syntax error line {e.lineno}: {e.msg}")

    # Write source to file
    try:
        Path(tool_path).write_text(source, encoding='utf-8')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write source: {str(e)}")

    # Re-register tool from updated file — merge manifest provenance first
    manifest_prov = _read_manifest_provenance(tool_path)
    merged_prov = {**(manifest_prov or {}), **prov}
    name_before = tool_name
    try:
        registry.unregister(name_before)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    try:
        import importlib.util, sys
        mod_name = f"ws_update_{tool_name.replace('-','_')}"
        spec = importlib.util.spec_from_file_location(mod_name, tool_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            td = getattr(mod, "TOOL_DEF", None)
            if td and isinstance(td, dict):
                cfg = ToolConfig(name=td.get("name", tool_name), description=td.get("description", ""), parameters=td.get("parameters", {}))
                new_tool = BaseTool(cfg)
                new_tool._execute_fn = td.get("execute")
                meta = getattr(new_tool._config, 'metadata', {}) or {}
                meta['provenance'] = merged_prov  # merge manifest + in-memory provenance
                setattr(new_tool._config, 'metadata', meta)
                registry.register(new_tool)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to re-register tool: {str(e)}")

    return {"status": "updated", "name": tool_name}


@router.post("/workspace/tools/{tool_name}/reload", response_model=Dict[str, Any])
async def reload_workspace_tool(tool_name: str):
    """Re-import a workspace tool .py file and re-register it in ToolRegistry."""
    from core.apps.tools.base import get_tool_registry, BaseTool, ToolConfig
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    meta = getattr(tool._config, 'metadata', {}) if hasattr(tool, '_config') else {}
    prov = (meta or {}).get('provenance', {}) if isinstance(meta, dict) else {}
    if not prov or prov.get('scope') != 'workspace':
        raise HTTPException(status_code=403, detail="Only workspace tools can be reloaded")

    tool_path = prov.get('tool_path', '')
    if not tool_path or not os.path.exists(tool_path):
        raise HTTPException(status_code=404, detail="Tool file not found on disk")

    # Merge manifest provenance (survives restart) with in-memory provenance
    merged_prov = {**(_read_manifest_provenance(tool_path) or {}), **prov}

    try:
        registry.unregister(tool_name)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    try:
        import importlib.util, sys
        mod_name = f"ws_reload_{tool_name.replace('-','_')}"
        spec = importlib.util.spec_from_file_location(mod_name, tool_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            td = getattr(mod, "TOOL_DEF", None)
            if td and isinstance(td, dict):
                cfg = ToolConfig(name=td.get("name", tool_name), description=td.get("description", ""), parameters=td.get("parameters", {}))
                new_tool = BaseTool(cfg)
                new_tool._execute_fn = td.get("execute")
                meta = getattr(new_tool._config, 'metadata', {}) or {}
                meta['provenance'] = merged_prov
                setattr(new_tool._config, 'metadata', meta)
                registry.register(new_tool)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload tool: {str(e)}")

    return {"status": "reloaded", "name": tool_name}
