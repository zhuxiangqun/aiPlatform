"""
Load workspace hook modules from ~/.aiplat/hooks.

Hook module contract (very small):

Each file <name>.py may define:
  - def register(hook_manager): ...

Where hook_manager is core.harness.infrastructure.hooks.HookManager.

This mirrors the "hooks" idea from Claude Code plugins, but keeps the
implementation safe-ish and optional (env controlled).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Dict
import importlib.util
import os


def _enabled() -> bool:
    return (os.getenv("AIPLAT_ENABLE_WORKSPACE_HOOKS", "true") or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def load_workspace_hooks(*, hook_manager: Any) -> Dict[str, Any]:
    if not _enabled():
        return {"enabled": False, "loaded": 0, "errors": []}
    base = Path.home() / ".aiplat" / "hooks"
    if not base.exists():
        return {"enabled": True, "loaded": 0, "errors": []}

    loaded = 0
    errors: List[dict] = []
    for py in sorted(base.glob("*.py"), key=lambda p: p.name):
        if py.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"aiplat_workspace_hook_{py.stem}", str(py))
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[attr-defined]
            reg = getattr(mod, "register", None)
            if callable(reg):
                reg(hook_manager)
            loaded += 1
        except Exception as e:
            errors.append({"file": str(py), "error": str(e)})
            continue
    return {"enabled": True, "loaded": loaded, "errors": errors}

