"""Tool listing lifecycle (draft → ready → published → listed → deprecated).

Engine/builtin tools (code-registered, not workspace-scoped) default to
``listed`` so application-layer Agents can bind them without a separate
上架 flow — same rule as engine-only Skills in approval deps.

Workspace tools still default to ``draft``. Explicit entries in
``tool_lifecycle.json`` / ``*.TOOL.manifest.json`` always win.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)

_VALID = frozenset({"draft", "ready", "published", "listed", "deprecated", "enabled"})
_DEFAULT = "draft"


def _home() -> Path:
    return Path(os.environ.get("AIPLAT_HOME", os.path.expanduser("~/.aiplat")))


def _store_path() -> Path:
    return _home() / "data" / "tool_lifecycle.json"


def _read_store() -> Dict[str, str]:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        out: Dict[str, str] = {}
        for k, v in data.items():
            key = str(k or "").strip()
            st = str(v or "").strip().lower()
            if key and st:
                out[key] = st
        return out
    except Exception:
        _logger.warning("Failed to read tool lifecycle store %s", path, exc_info=True)
        return {}


def _write_store(data: Dict[str, str]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _manifest_path_for_tool(tool_name: str, tool_path: Optional[str] = None) -> Optional[Path]:
    if tool_path:
        return Path(str(tool_path).replace(".py", ".TOOL.manifest.json"))
    tools_dir = Path(os.getenv("AIPLAT_TOOLS_PATH", str(_home() / "tools")))
    candidate = tools_dir / f"{tool_name}.TOOL.manifest.json"
    return candidate if candidate.exists() else None


def _read_manifest_status(tool_name: str, tool_path: Optional[str] = None) -> Optional[str]:
    mp = _manifest_path_for_tool(tool_name, tool_path)
    if mp is None or not mp.exists():
        return None
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            st = str(data.get("status") or "").strip().lower()
            return st or None
    except Exception:
        _logger.warning("Failed to read tool manifest status %s", mp, exc_info=True)
    return None


def _write_manifest_status(tool_name: str, status: str, tool_path: Optional[str] = None) -> None:
    """Best-effort mirror into workspace TOOL.manifest.json."""
    mp = _manifest_path_for_tool(tool_name, tool_path)
    if mp is None:
        tools_dir = Path(os.getenv("AIPLAT_TOOLS_PATH", str(_home() / "tools")))
        py = tools_dir / f"{tool_name}.py"
        if not py.exists():
            return
        mp = Path(str(py).replace(".py", ".TOOL.manifest.json"))
    try:
        manifest: Dict[str, Any] = {}
        if mp.exists():
            try:
                loaded = json.loads(mp.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    manifest = loaded
            except Exception:  # noqa: cleanup-best-effort
                pass
        manifest["status"] = status
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        _logger.warning("Failed to write tool manifest status %s", mp, exc_info=True)


def _is_engine_registered(tool_name: str) -> bool:
    """True when name is in the tool registry and not a workspace-scoped tool.

    Matches ``GET /tools`` semantics: missing provenance.scope ⇒ engine/builtin.
    """
    try:
        from core.apps.tools.base import get_tool_registry

        tool = get_tool_registry().get(tool_name)
        if tool is None:
            return False
        meta = getattr(getattr(tool, "_config", None), "metadata", None) or {}
        if not isinstance(meta, dict):
            return True
        prov = meta.get("provenance") or {}
        if isinstance(prov, dict) and str(prov.get("scope") or "").strip().lower() == "workspace":
            return False
        return True
    except Exception:
        return False


def get_tool_status(tool_name: str, *, tool_path: Optional[str] = None) -> str:
    """Return lifecycle status.

    Precedence: explicit store → workspace manifest → engine builtin ``listed``
    → default ``draft`` (workspace-created tools).

    Engine/builtin tools are platform-owned and safe for application-layer
    binding without a separate 上架 flow (aligned with engine-only Skills).
    Explicit store/manifest still wins (e.g. admin can deprecate).
    """
    name = str(tool_name or "").strip()
    if not name:
        return _DEFAULT
    store = _read_store()
    if name in store:
        return store[name]
    ms = _read_manifest_status(name, tool_path)
    if ms:
        return ms
    if _is_engine_registered(name):
        return "listed"
    return _DEFAULT


def set_tool_status(tool_name: str, status: str, *, tool_path: Optional[str] = None) -> str:
    """Persist lifecycle status. Returns normalized status."""
    name = str(tool_name or "").strip()
    if not name:
        raise ValueError("tool_name is required")
    st = str(status or "").strip().lower()
    if st not in _VALID:
        raise ValueError(f"invalid tool status: {status!r}")
    # ``enabled`` is a legacy alias used by some UIs; treat as draft for listing gate.
    if st == "enabled":
        st = "draft"
    store = _read_store()
    store[name] = st
    _write_store(store)
    _write_manifest_status(name, st, tool_path=tool_path)
    return st


def list_tool_statuses() -> Dict[str, str]:
    """Return all known tool→status entries (store + manifests not fully scanned)."""
    return dict(_read_store())
