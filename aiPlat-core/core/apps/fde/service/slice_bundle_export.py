"""Five-products slice: thin Bundle export orchestration (KG-EDGE-01 / KG-BUNDLE-01).

Reuses workspace ``scripts/export_pi_bundle.py`` — does not create a parallel publisher.
``permission_claims`` in export meta are declarative only and must not authorize alone.
"""
from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_log = logging.getLogger(__name__)

# core/apps/fde/service → workspace root
_WORKSPACE = Path(__file__).resolve().parents[5]
_EXPORT_SCRIPT = _WORKSPACE / "scripts" / "export_pi_bundle.py"


def _resolve_app_home(app_home: str) -> Path:
    raw = (app_home or "").strip()
    if not raw:
        raise ValueError("app_home required")
    p = Path(raw)
    if not p.is_absolute():
        p = (_WORKSPACE / p).resolve()
    else:
        p = p.resolve()
    return p


def export_slice_bundle(
    *,
    scenario_id: str,
    app_home: str,
    out_dir: Optional[str] = None,
    runtime_mode: str = "thin",
) -> Dict[str, Any]:
    """Export a Pi thin package for a slice scenario.

    Returns ``{ok, bundle_id, out_dir, integrity, export_meta, permission_claims_note, ...}``.
    Never returns ok=True on failure.
    """
    sid = (scenario_id or "").strip()
    if not sid:
        return {"ok": False, "error": "scenario_id required"}

    mode = (runtime_mode or "thin").strip().lower()
    if mode != "thin":
        return {
            "ok": False,
            "error": "slice export requires runtime_mode=thin (Enterprise not in scope)",
        }

    try:
        src = _resolve_app_home(app_home)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    if not src.is_dir():
        return {"ok": False, "error": f"app_home missing: {src}"}
    manifest = src / "agent_manifest.json"
    if not manifest.is_file():
        return {"ok": False, "error": f"no agent_manifest.json under {src}"}

    if not _EXPORT_SCRIPT.is_file():
        return {"ok": False, "error": f"export script missing: {_EXPORT_SCRIPT}"}

    dest: Path
    if out_dir and str(out_dir).strip():
        dest = Path(str(out_dir).strip())
        if not dest.is_absolute():
            dest = (_WORKSPACE / dest).resolve()
    else:
        home = Path(get_aiplat_home())
        dest = home / "five_products_slice" / sid / "bundle"

    spec = importlib.util.spec_from_file_location("aiplat_export_pi_bundle_slice", _EXPORT_SCRIPT)
    if spec is None or spec.loader is None:
        return {"ok": False, "error": "cannot load export_pi_bundle.py"}
    mod = importlib.util.module_from_spec(spec)
    ws = str(_WORKSPACE)
    if ws not in sys.path:
        sys.path.insert(0, ws)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        _log.warning("load export script failed: %s", exc, exc_info=True)
        return {"ok": False, "error": f"load export script: {exc}"}

    export_fn = getattr(mod, "export_bundle", None)
    if export_fn is None:
        return {"ok": False, "error": "export_bundle() missing"}

    try:
        written = export_fn(
            app_home=src,
            out=dest,
            project_id=sid,
            runtime_mode="thin",
        )
    except SystemExit as exc:
        return {"ok": False, "error": f"export aborted: {exc}", "app_home": str(src)}
    except Exception as exc:
        _log.warning("slice bundle export failed: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc), "app_home": str(src)}

    written_p = Path(written)
    export_meta: Dict[str, Any] = {}
    meta_path = written_p / "aiplat-export.json"
    if meta_path.is_file():
        try:
            export_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            export_meta = {"parse_error": True}

    integrity: Dict[str, Any] = {}
    if isinstance(export_meta, dict):
        integrity = {
            k: export_meta.get(k)
            for k in ("bundle_version", "git_sha", "build_time", "integrity", "bundle_sha256")
            if k in export_meta or export_meta.get("build")
        }
        build = export_meta.get("build")
        if isinstance(build, dict):
            integrity.update({k: build.get(k) for k in ("bundle_version", "git_sha", "build_time") if build.get(k)})

    bundle_id = (
        (export_meta.get("bundle_version") if isinstance(export_meta, dict) else None)
        or (integrity.get("bundle_version") if isinstance(integrity, dict) else None)
        or f"{sid}:{written_p.name}"
    )

    claims = []
    if isinstance(export_meta, dict):
        raw_claims = export_meta.get("permission_claims") or export_meta.get("permissions")
        if isinstance(raw_claims, list):
            claims = raw_claims

    return {
        "ok": True,
        "scenario_id": sid,
        "bundle_id": str(bundle_id),
        "out_dir": str(written_p),
        "app_home": str(src),
        "runtime_mode": "thin",
        "integrity": integrity,
        "export_meta": export_meta if isinstance(export_meta, dict) else {},
        "permission_claims": claims,
        "permission_claims_note": (
            "permission_claims are declarative only and MUST NOT authorize alone; "
            "server-side PolicyGate / identity remains authoritative."
        ),
        "hint": f"AIPLAT_APP_HOME={written_p} pi -e {written_p}",
    }
