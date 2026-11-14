"""Export deployed Agent apps as Pi Packages (thin user-side Runtime).

Best-effort helper used after deploy and via explicit API. Never raises into
the deploy critical path — callers should catch and surface warnings.
"""
from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_log = logging.getLogger("aiplat.builder.pi_bundle")

# aiPlat-platform/builder → workspace root (…/aiPlatform)
_WORKSPACE = Path(__file__).resolve().parents[2]
_EXPORT_SCRIPT = _WORKSPACE / "scripts" / "export_pi_bundle.py"

# Platform controls that do NOT travel with a Pi export package (P0-4).
_PI_LOST_CONTROLS = (
    "PolicyGate",
    "ApprovalGate",
    "AuditLogger",
    "PIIDetector",
    "TenantIsolation",
    "RateLimit",
)


def write_pi_security_disclosure(bundle_dir: Path, *, project_id: str) -> Dict[str, Any]:
    """Auto-write Pi security disclosure + artifact.security.json (P0-4).

    Args:
        bundle_dir: bundle_dir 参数。
        project_id: project 标识。
    """
    from builder.artifact_security_manifest import build_manifest, write_manifest

    bundle_dir = Path(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    claim = (
        "本 Pi 导出包不继承平台 PolicyGate/ApprovalGate 等横切控制；"
        "不得默认宣称「平台级安全」。security_certification=false。"
    )
    disclosure = {
        "project_id": project_id,
        "package_type": "pi",
        "platform_controls_lost_on_export": list(_PI_LOST_CONTROLS),
        "platform_controls_inherited": [],
        "claim_boundary": claim,
        "security_certification": False,
        "generated_by": "pi_bundle_export.write_pi_security_disclosure",
    }
    disc_path = bundle_dir / "SECURITY_DISCLOSURE.json"
    import json

    disc_path.write_text(json.dumps(disclosure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = build_manifest(
        artifact_id=f"pi:{project_id}",
        artifact_type="pi",
        owner="pi_export",
        platform_controls_inherited=[],
        platform_controls_lost_on_export=list(_PI_LOST_CONTROLS),
        sast={"status": "pass", "tool": "na", "detail": "pi_export_disclosure_only"},
        secrets_scan={"status": "pass", "detail": "deferred_to_source_gate"},
        deps_scan={"status": "pass", "detail": "deferred_to_source_gate"},
        authz_smoke={"status": "na", "evidence": "Pi export has no platform authz runtime"},
        claim_boundary=claim,
    )
    man_path = write_manifest(bundle_dir / "artifact.security.json", manifest)
    return {
        "ok": True,
        "disclosure_path": str(disc_path),
        "manifest_path": str(man_path),
        "platform_controls_lost_on_export": list(_PI_LOST_CONTROLS),
        "claim_boundary": claim,
    }


def workspace_root() -> Path:
    """workspace_root。
    """
    return _WORKSPACE


def default_out_dir(project_id: str) -> Path:
    """default_out_dir。

    Args:
        project_id: project 标识。
    """
    home = Path(get_aiplat_home())
    return home / "apps" / project_id / "pi-bundle"


def app_home_for(project_id: str) -> Path:
    """app_home_for。

    Args:
        project_id: project 标识。
    """
    home = Path(get_aiplat_home())
    return home / "apps" / project_id / "current"


def export_pi_bundle_for_project(
    project_id: str,
    *,
    app_home: Optional[str] = None,
    out: Optional[str] = None,
) -> Dict[str, Any]:
    """Export Agent app at apps/{id}/current → Pi Package directory.

    Args:
        project_id: project 标识。
        app_home: app_home 参数。
        out: out 参数。
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

    # P0-4: exporter-auto security disclosure (never hand-written README as sole source)
    disclosure = write_pi_security_disclosure(Path(written), project_id=pid)

    return {
        "ok": True,
        "project_id": pid,
        "app_home": str(src),
        "pi_bundle": str(written),
        "security_disclosure": disclosure,
        "hint": f"AIPLAT_APP_HOME={written} pi -e {written}",
        "http_hint": f"AIPLAT_APP_HOME={written} node packages/aiplat-pi-runtime/bin/aiplat-http.mjs",
    }


def try_export_after_deploy(project_id: str, app_home: str) -> Dict[str, Any]:
    """Non-throwing wrapper for deploy path.

    Args:
        project_id: project 标识。
        app_home: app_home 参数。
    """
    try:
        return export_pi_bundle_for_project(project_id, app_home=app_home)
    except Exception as exc:
        _log.debug("try_export_after_deploy: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc), "skipped": True}


def zip_pi_bundle_for_project(
    project_id: str,
    *,
    app_home: Optional[str] = None,
) -> Tuple[Optional[Path], Dict[str, Any]]:
    """Ensure Pi Package exists, then zip it for download.

    Args:
        project_id: project 标识。
        app_home: app_home 参数。
    """
    pid = str(project_id or "").strip()
    existing = default_out_dir(pid)
    if (
        not app_home
        and existing.is_dir()
        and (existing / "package.json").is_file()
        and (existing / "agent_manifest.json").is_file()
    ):
        meta: Dict[str, Any] = {
            "ok": True,
            "project_id": pid,
            "pi_bundle": str(existing),
            "reused": True,
        }
    else:
        meta = export_pi_bundle_for_project(pid, app_home=app_home)
        if not meta.get("ok"):
            return None, meta
    bundle = Path(str(meta.get("pi_bundle") or ""))
    if not bundle.is_dir():
        return None, {**meta, "ok": False, "error": f"pi_bundle missing: {bundle}"}

    # Prefer stable path next to bundle; fall back to temp
    home = Path(get_aiplat_home())
    out_dir = home / "apps" / str(project_id).strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_base = out_dir / f"pi-bundle-{project_id}"
    try:
        # make_archive adds .zip
        written = Path(
            shutil.make_archive(str(zip_base), "zip", root_dir=str(bundle.parent), base_dir=bundle.name)
        )
        meta = {
            **meta,
            "zip": str(written),
            "download_name": f"aiplat-pi-{project_id}.zip",
            "ephemeral_zip": False,
        }
        return written, meta
    except Exception as exc:
        _log.warning("zip pi bundle failed for %s: %s", project_id, exc, exc_info=True)
        try:
            tmp = Path(tempfile.mkdtemp(prefix="aiplat-pi-zip-"))
            written = Path(
                shutil.make_archive(
                    str(tmp / f"pi-bundle-{project_id}"),
                    "zip",
                    root_dir=str(bundle.parent),
                    base_dir=bundle.name,
                )
            )
            return written, {
                **meta,
                "ok": True,
                "zip": str(written),
                "download_name": f"aiplat-pi-{project_id}.zip",
                "ephemeral_zip": True,
            }
        except Exception as exc2:
            return None, {**meta, "ok": False, "error": str(exc2)}
