"""Export deployed Agent apps as Pi Packages (thin user-side Runtime).

Best-effort helper used after deploy and via explicit API. Never raises into
the deploy critical path — callers should catch and surface warnings.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_log = logging.getLogger("aiplat.builder.pi_bundle")

# aiPlat-platform/builder → workspace root (…/aiPlatform)
_WORKSPACE = Path(__file__).resolve().parents[2]
_EXPORT_SCRIPT = _WORKSPACE / "scripts" / "export_pi_bundle.py"


def workspace_root() -> Path:
    return _WORKSPACE


def default_out_dir(project_id: str) -> Path:
    home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
    return home / "apps" / project_id / "pi-bundle"


def app_home_for(project_id: str) -> Path:
    home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
    return home / "apps" / project_id / "current"


def export_pi_bundle_for_project(
    project_id: str,
    *,
    app_home: Optional[str] = None,
    out: Optional[str] = None,
) -> Dict[str, Any]:
    """Export Agent app at apps/{id}/current → Pi Package directory.

    Returns a dict with ok/error and paths. Requires agent_manifest.json.
    """
    pid = str(project_id or "").strip()
    if not pid:
        return {"ok": False, "error": "project_id required"}

    src = Path(app_home) if app_home else app_home_for(pid)
    if not src.is_dir():
        return {"ok": False, "error": f"app_home missing: {src}"}
    manifest = src / "agent_manifest.json"
    if not manifest.is_file():
        return {
            "ok": False,
            "error": "no agent_manifest.json — skip Pi export (code-mode or incomplete deploy)",
            "skipped": True,
            "app_home": str(src),
        }

    if not _EXPORT_SCRIPT.is_file():
        return {"ok": False, "error": f"export script missing: {_EXPORT_SCRIPT}"}

    # Import export_bundle without relying on PYTHONPATH
    import importlib.util

    spec = importlib.util.spec_from_file_location("aiplat_export_pi_bundle", _EXPORT_SCRIPT)
    if spec is None or spec.loader is None:
        return {"ok": False, "error": "cannot load export_pi_bundle.py"}
    mod = importlib.util.module_from_spec(spec)
    # Ensure workspace on path for any relative imports inside script (none today)
    ws = str(_WORKSPACE)
    if ws not in sys.path:
        sys.path.insert(0, ws)
    spec.loader.exec_module(mod)
    export_fn = getattr(mod, "export_bundle", None)
    if export_fn is None:
        return {"ok": False, "error": "export_bundle() missing in script"}

    dest = Path(out) if out else default_out_dir(pid)
    try:
        written = export_fn(app_home=src, out=dest, project_id=pid)
    except SystemExit as exc:
        return {"ok": False, "error": f"export aborted: {exc}", "app_home": str(src)}
    except Exception as exc:
        _log.warning("pi bundle export failed for %s: %s", pid, exc, exc_info=True)
        return {"ok": False, "error": str(exc), "app_home": str(src)}

    return {
        "ok": True,
        "project_id": pid,
        "app_home": str(src),
        "pi_bundle": str(written),
        "hint": f"AIPLAT_APP_HOME={written} pi -e {written}",
        "http_hint": f"AIPLAT_APP_HOME={written} node packages/aiplat-pi-runtime/bin/aiplat-http.mjs",
    }


def try_export_after_deploy(project_id: str, app_home: str) -> Dict[str, Any]:
    """Non-throwing wrapper for deploy path."""
    try:
        return export_pi_bundle_for_project(project_id, app_home=app_home)
    except Exception as exc:
        _log.debug("try_export_after_deploy: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc), "skipped": True}
