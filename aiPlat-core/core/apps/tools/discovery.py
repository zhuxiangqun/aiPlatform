"""Tool Discovery — dynamic file-system scanning for user-defined tools.

Scans ~/.aiplat/tools/ for Python files containing TOOL_DEF exports.
Registers discovered tools into the global ToolRegistry at startup.

Per CLAUDE.md §5.30: called from core/server.py lifespan.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_tools_dir() -> Path:
    return Path(os.getenv("AIPLAT_TOOLS_PATH",
        os.path.join(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")), "tools")))


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

            if isinstance(tool_def, dict):
                results.append({
                    "id": tool_def.get("id", fpath.stem),
                    "name": tool_def.get("name", fpath.stem),
                    "description": tool_def.get("description", ""),
                    "parameters": tool_def.get("parameters", {}),
                    "execute": tool_def.get("execute"),
                    "call_type": tool_def.get("call_type", "direct"),
                    "security_level": tool_def.get("security_level", "low"),
                    "module_path": str(fpath),
                })
            elif hasattr(tool_def, "id"):
                results.append({
                    "id": getattr(tool_def, "id", fpath.stem),
                    "name": getattr(tool_def, "name", fpath.stem),
                    "description": getattr(tool_def, "description", ""),
                    "parameters": getattr(tool_def, "parameters", {}),
                    "execute": getattr(tool_def, "execute", None),
                    "call_type": getattr(tool_def, "call_type", "direct"),
                    "security_level": getattr(tool_def, "security_level", "low"),
                    "module_path": str(fpath),
                })

        return results

    def register_all(self) -> int:
        """Scan and register all discovered tools into the global ToolRegistry."""
        discovered = self.scan()
        if not discovered:
            return 0

        try:
            from core.apps.tools.registry import ToolRegistry
            registry: ToolRegistry = ToolRegistry()
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
                registry.register(_make_discovery_tool(d))
                registered += 1
                logger.info(f"Registered user tool: {d['id']} (from {d['module_path']})")
            except Exception:
                logger.debug(f"Failed to register tool: {d['id']}", exc_info=True)

        return registered


def get_tool_discovery() -> ToolDiscovery:
    return ToolDiscovery()


def _make_discovery_tool(d: dict) -> Any:
    """Build a BaseTool-compatible object from a discovered tool dict."""
    from core.apps.tools.base import BaseTool
    class _DiscoveredTool(BaseTool):
        def __init__(self):
            super().__init__(
                name=d.get("name", ""),
                description=d.get("description", ""),
            )
            self._execute_fn = d.get("execute")
        async def execute(self, **params):
            if self._execute_fn:
                return self._execute_fn(params)
            return {"error": "no execute function"}
    return _DiscoveredTool()
