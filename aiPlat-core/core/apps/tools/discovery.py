"""Tool Discovery — dynamic file-system scanning for user-defined tools.

Scans ~/.aiplat/tools/ for Python files containing TOOL_DEF exports.
Registers discovered tools into the global ToolRegistry at startup.

Per CLAUDE.md §5.30: called from core/server.py lifespan.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_tools_dir() -> Path:
    return Path(os.getenv("AIPLAT_TOOLS_PATH",
        os.path.join(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")), "tools")))


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _read_tool_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Read optional TOOL.manifest.json companion file."""
    if not manifest_path.exists():
        return {}
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _verify_tool_signature(tool_id: str, entry: Dict[str, Any]) -> None:
    """Best-effort: verify TOOL.manifest.json signature against tool file."""
    try:
        from core.harness.infrastructure.crypto.signature import verify_skill_signature
        from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map
        from core.harness.kernel.runtime import get_kernel_runtime
        import asyncio
        sig = entry.get("provenance", {}).get("signature")
        bundle = entry.get("integrity", {}).get("bundle_sha256")
        if sig and bundle:
            rt = get_kernel_runtime()
            store = getattr(rt, "execution_store", None) if rt else None
            import concurrent.futures as _cf
            with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
                trusted = _pool.submit(asyncio.run, get_trusted_skill_pubkeys_map(store)).result(timeout=10) if store else {}
            verify_skill_signature(skill_id=tool_id, version="0.1.0", bundle_sha256=bundle, signature=sig, trusted_keys=trusted)
    except Exception as e:
        logging.debug(str(e), exc_info=True)


class ToolDiscovery:
    """Scans user tool directories and registers discovered tools."""

    def __init__(self, tools_dir: Optional[Path] = None):
        self._tools_dir = tools_dir or _default_tools_dir()

    def scan(self) -> List[Dict[str, Any]]:
        """Scan the tools directory for executable tool definitions.

        Each .py file in the directory may export a TOOL_DEF dict or callable.
        Returns list of {id, name, description, module_path} for discovered tools.
        """
        results: List[Dict[str, Any]] = []
        if not self._tools_dir.exists():
            return results

        for fpath in sorted(self._tools_dir.glob("*.py")):
            try:
                discovered = self._load_tool_file(fpath)
                if discovered:
                    results.extend(discovered)
            except Exception:
                logger.debug(f"Failed to load tool from {fpath}", exc_info=True)

        return results

    def _load_tool_file(self, fpath: Path) -> List[Dict[str, Any]]:
        module_name = f"aiplat_user_tool_{fpath.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(fpath))
        if spec is None or spec.loader is None:
            return []
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Compute file integrity (SHA256 of the .py file = bundle for flat-file tools)
        file_sha256 = _sha256_file(fpath)

        # Read optional companion manifest, auto-create if missing
        manifest_path = fpath.parent / f"{fpath.stem}.TOOL.manifest.json"
        manifest = _read_tool_manifest(manifest_path)
        if not manifest:
            manifest = {"version": "1.0.0"}
            try:
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        results = []
        for attr_name in dir(module):
            if not attr_name.startswith("TOOL_DEF"):
                continue
            tool_def = getattr(module, attr_name, None)
            if tool_def is None:
                continue

            if callable(tool_def):
                try:
                    from core.harness.interfaces.tool import ToolDef
                    tool_def = tool_def()
                except Exception:
                    continue

            tool_id = tool_def.get("id", fpath.stem) if isinstance(tool_def, dict) else getattr(tool_def, "id", fpath.stem)

            entry: Dict[str, Any] = {}
            if isinstance(tool_def, dict):
                entry = {
                    "id": tool_id,
                    "name": tool_def.get("name", fpath.stem),
                    "description": tool_def.get("description", ""),
                    "parameters": tool_def.get("parameters", {}),
                    "execute": tool_def.get("execute"),
                    "call_type": tool_def.get("call_type", "direct"),
                    "security_level": tool_def.get("security_level", "low"),
                    "module_path": str(fpath),
                }
            elif hasattr(tool_def, "id"):
                entry = {
                    "id": tool_id,
                    "name": getattr(tool_def, "name", fpath.stem),
                    "description": getattr(tool_def, "description", ""),
                    "parameters": getattr(tool_def, "parameters", {}),
                    "execute": getattr(tool_def, "execute", None),
                    "call_type": getattr(tool_def, "call_type", "direct"),
                    "security_level": getattr(tool_def, "security_level", "low"),
                    "module_path": str(fpath),
                }

            # Enrich with provenance and integrity metadata
            entry["provenance"] = {
                "source_type": "filesystem",
                "scope": "workspace",
                "tool_path": str(fpath),
            }
            if manifest:
                # Read provenance from structured sub-dict first, then root-level fallback
                mp = manifest.get("provenance", {}) if isinstance(manifest, dict) else {}
                entry["provenance"].update({
                    "publisher": mp.get("publisher") or manifest.get("publisher"),
                    "source": mp.get("source") or manifest.get("source"),
                    "version": mp.get("version") or manifest.get("version"),
                    "signature": mp.get("signature") or manifest.get("signature"),
                    "signature_verified": mp.get("signature_verified") or manifest.get("signature_verified", False),
                    "signature_key_id": mp.get("signature_key_id") or manifest.get("signature_key_id", ""),
                    "manifest_sha256": _sha256_file(manifest_path),
                })
            # Workspace tools without external source → mark as locally created
            if not entry["provenance"].get("source"):
                entry["provenance"]["source"] = "local"
            entry["integrity"] = {
                "bundle_sha256": file_sha256,
                "file_path": str(fpath),
            }

            results.append(entry)

        return results

    def register_all(self) -> int:
        """Scan and register all discovered tools into the global ToolRegistry."""
        discovered = self.scan()
        if not discovered:
            return 0

        try:
            from core.apps.tools.base import get_tool_registry
            registry = get_tool_registry()
        except Exception:
            return 0

        registered = 0
        for d in discovered:
            if d.get("execute") is None:
                continue
            try:
                # Discovered tool dicts can be wrapped as BaseTool-like objects
                # for ToolRegistry registration. ToolDef is not a real class;
                # use the dict data directly to construct a minimal tool adapter.
                tool = _make_discovery_tool(d)
                # Attach provenance and integrity metadata
                if hasattr(tool, '_config'):
                    tool._config.metadata = getattr(tool._config, 'metadata', {}) or {}
                    tool._config.metadata['provenance'] = d.get('provenance', {})
                    tool._config.metadata['integrity'] = d.get('integrity', {})
                registry.register(tool)
                # Best-effort signature verification
                sig = d.get("provenance", {}).get("signature")
                if sig:
                    _verify_tool_signature(d["id"], d)
                registered += 1
                logger.info(f"Registered user tool: {d['id']} (from {d['module_path']})")
            except Exception:
                logger.debug(f"Failed to register tool: {d['id']}", exc_info=True)

        return registered


def get_tool_discovery() -> ToolDiscovery:
    return ToolDiscovery()


def _make_discovery_tool(d: dict) -> Any:
    """Build a BaseTool-compatible object from a discovered tool dict.

    Extracts MCP permission metadata from inputSchema if present.
    Tool permissions are enforced by PolicyGate via the standard
    sys_tool_call path — same as locally-registered Tools.
    """
    from core.apps.tools.base import BaseTool, ToolConfig
    class _DiscoveredTool(BaseTool):
        def __init__(self):
            tool_params = d.get("parameters") or d.get("inputSchema") or {}
            super().__init__(
                ToolConfig(
                    name=d.get("name", ""),
                    description=d.get("description", ""),
                    parameters=tool_params,
                )
            )
            self._execute_fn = d.get("execute")
            permissions = tool_params.get("required_permissions", [])
            if isinstance(permissions, list):
                self._mcp_permissions = permissions
        async def execute(self, params=None, **kwargs):
            from core.harness.interfaces.tool import ToolResult
            try:
                if self._execute_fn:
                    if params is None and kwargs:
                        return ToolResult(success=True, output=self._execute_fn(kwargs))
                    if isinstance(params, dict):
                        return ToolResult(success=True, output=self._execute_fn(params))
                return ToolResult(success=False, error="no execute function")
            except Exception as e:
                return ToolResult(success=False, error=str(e))
    return _DiscoveredTool()
