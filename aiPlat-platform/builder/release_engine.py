"""L5 module-level CI/CD release engine (plan-app-factory-l5 §3.1/§3.2/§3.5).

- Versioned artifacts: releases/v{ts}/current + current pointer (symlink or
  pointer file for Windows compat).
- Release state machine: building → ready → canary → full → rolled_back
  (controlled flow, not one-shot overwrite).
- Canary semantics: status marker for "small-ratio validation"; promote to full
  or roll back to a historical version (append-only history).
"""
from __future__ import annotations

import os
import shutil
import time
from typing import Any, Dict, List

# State machine transitions
_BUILDING = "building"
_READY = "ready"
_CANARY = "canary"
_FULL = "full"
_ROLLED_BACK = "rolled_back"

_VALID_TRANSITIONS = {
    _BUILDING: {_READY},
    _READY: {_CANARY},
    _CANARY: {_FULL, _ROLLED_BACK},
    _FULL: {_ROLLED_BACK},
    _ROLLED_BACK: set(),
}

_POINTER_FILE = "current.txt"  # Windows-compatible pointer; symlink used when possible


def _apps_home(project_id: str) -> str:
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "apps", project_id)


def release_root(project_id: str) -> str:
    return os.path.join(_apps_home(project_id), "releases")


def current_dir(project_id: str) -> str:
    """Resolve the current pointer → releases/v{ts}/current path."""
    root = release_root(project_id)
    if not os.path.isdir(root):
        return ""
    # pointer file first (portable), then symlink
    pf = os.path.join(_apps_home(project_id), _POINTER_FILE)
    if os.path.isfile(pf):
        try:
            with open(pf, "r", encoding="utf-8") as fh:
                rel = fh.read().strip()
            if rel:
                return os.path.join(root, rel, "current")
        except OSError:
            pass  # noqa: cleanup-best-effort — unreadable pointer → fall through to symlink
    sym = os.path.join(_apps_home(project_id), "current")
    if os.path.islink(sym):
        return sym
    return ""


def _write_pointer(project_id: str, version: str) -> None:
    """Point current → releases/{version}/current (symlink, fallback pointer file)."""
    apps = _apps_home(project_id)
    os.makedirs(apps, exist_ok=True)
    sym = os.path.join(apps, "current")
    try:
        if os.path.islink(sym) or os.path.exists(sym):
            if os.path.islink(sym):
                os.unlink(sym)
            else:
                # existing dir/current from legacy deploy — rename aside? keep pointer file route
                os.remove(sym) if os.path.isfile(sym) else None
        os.symlink(os.path.join("releases", version, "current"), sym)
        # also write pointer file (portable fallback)
        with open(os.path.join(apps, _POINTER_FILE), "w", encoding="utf-8") as fh:
            fh.write(version)
        return
    except OSError:
        pass  # noqa: cleanup-best-effort — symlink unavailable (e.g. sandbox) → pointer file only
    with open(os.path.join(apps, _POINTER_FILE), "w", encoding="utf-8") as fh:
        fh.write(version)


def create_release(project_id: str, module_id: str, src_dir: str,
                   new_files: Dict[str, str], pass_rate_source: str = "unknown") -> Dict[str, Any]:
    """Merge post-merge code into a versioned artifact (building → ready).

    src_dir: module imported root (baseline). new_files: merge_previews
    new_content overrides. Returns release record.
    """
    version = f"v{time.strftime('%Y%m%d%H%M%S')}"
    dst = os.path.join(release_root(project_id), version, "current")
    os.makedirs(dst, exist_ok=True)
    # baseline = imported originals
    if os.path.isdir(src_dir):
        for root, _dirs, files in os.walk(src_dir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, src_dir)
                out = os.path.join(dst, rel)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                shutil.copy2(full, out)
    # overlay merge new versions
    for rel, content in (new_files or {}).items():
        out = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(content)
    release = {
        "version": version,
        "module_id": module_id,
        "status": _READY,
        "pass_rate_source": pass_rate_source,
        "canary_weight": 0,  # L5 v2: routing weight (0=off, 10/50/100=percent)
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": len(new_files or {}),
    }
    # building → ready (instant; artifact written above)
    return release


def set_release_status(project_id: str, releases: List[Dict], version: str,
                       target: str, *, target_version: str = "",
                       canary_weight: int = 0) -> Dict[str, Any]:
    """Transition a release to canary/full, or roll back (switch current pointer).

    Rollback: current release → rolled_back; current pointer switches to
    target_version (a historical release, default = latest other applied one).
    L5 v2: canary sets canary_weight (routing percent); full forces 100.
    """
    rel = next((r for r in releases if r.get("version") == version), None)
    if not rel:
        raise ValueError(f"版本 {version} 不存在")
    current = rel.get("status", "")
    if target not in _VALID_TRANSITIONS.get(current, set()):
        raise ValueError(f"状态不允许从 {current} → {target}（合法：{_VALID_TRANSITIONS.get(current, set())}）")
    rel["status"] = target
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    if target == _CANARY:
        rel["canary_weight"] = int(canary_weight) if canary_weight else int(rel.get("canary_weight") or 10)
    elif target == _FULL:
        rel["full_at"] = now
        rel["canary_weight"] = 100  # full = 100% routing
        _write_pointer(project_id, version)
    elif target == _ROLLED_BACK:
        rel["rolled_back_at"] = now
        rel["canary_weight"] = 0
        # switch pointer to target_version (or latest non-rolled-back other release)
        target_version = target_version or _latest_active(releases, version)
        if target_version:
            _write_pointer(project_id, target_version)
    return rel


def _latest_active(releases: List[Dict], exclude_version: str) -> str:
    """Latest release that is not the excluded one and not rolled_back."""
    for r in reversed(releases):
        if r.get("version") != exclude_version and r.get("status") != _ROLLED_BACK:
            return r.get("version", "")
    return ""


def apply_release(project_id: str, src_dir: str, new_files: Dict[str, str]) -> Dict[str, Any]:
    """Convenience: create_release + set current pointer (used by release endpoint)."""
    release = create_release(project_id, "default", src_dir, new_files)
    _write_pointer(project_id, release["version"])
    return release
