"""Archived offline bridge for Pi coding exec (factory-in way 4).

**Merge-closed (2026-10-14)** — no longer called from Workspace Execute /
``core_facade``. Kept for manual CLI/probes only. See
``docs/FACTORY_IN_EXPERIMENT.md`` §⓪.

Feature flag ``AIPLAT_PI_CODING_EXECUTOR`` still gates this module when invoked
directly; it has **no** production Execute effect.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def is_enabled() -> bool:
    """True when AIPLAT_PI_CODING_EXECUTOR is 1/true/yes/on."""
    return _env_truthy("AIPLAT_PI_CODING_EXECUTOR")


def allow_host_cwd() -> bool:
    """True when AIPLAT_PI_CODING_ALLOW_HOST permits preferred_cwd (dev only)."""
    return _env_truthy("AIPLAT_PI_CODING_ALLOW_HOST")


def resolve_coding_cwd(preferred_cwd: str = "") -> Path:
    """Pick working directory for Pi coding.

    - If allow_host and preferred_cwd is an existing directory → use it.
    - Otherwise (including allow_host with empty preferred_cwd) → temp under
      AIPLAT_PI_CODING_SANDBOX_ROOT or TMPDIR.
    """
    preferred = (preferred_cwd or "").strip()
    if allow_host_cwd() and preferred:
        p = Path(preferred).expanduser()
        if p.is_dir():
            return p.resolve()

    root = (os.getenv("AIPLAT_PI_CODING_SANDBOX_ROOT") or "").strip()
    if root:
        base = Path(root).expanduser()
        base.mkdir(parents=True, exist_ok=True)
    else:
        base = Path(os.getenv("TMPDIR") or tempfile.gettempdir())
    return Path(tempfile.mkdtemp(prefix="aiplat_pi_coding_", dir=str(base)))


def _load_run_coding_exec():
    """Prefer importlib load of scripts/coding_exec.py::run_coding_exec."""
    here = Path(__file__).resolve()
    script = here.parents[1] / "scripts" / "coding_exec.py"
    if not script.is_file():
        raise FileNotFoundError(f"coding_exec.py not found: {script}")
    spec = importlib.util.spec_from_file_location("aiplat_coding_exec", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load coding_exec from {script}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "run_coding_exec", None)
    if not callable(fn):
        raise AttributeError("run_coding_exec missing on coding_exec module")
    return fn


def run_workspace_coding_via_pi(
    *,
    prompt: str,
    preferred_cwd: str = "",
    model: str = "",
    timeout_sec: int = 300,
) -> Dict[str, Any]:
    """Optional Pi print-mode coding for Workspace Execute.

    Returns ``{"ok": False, "skipped": True, "reason": "disabled"}`` when flag off.
    """
    if not is_enabled():
        return {"ok": False, "skipped": True, "reason": "disabled"}

    model_s = (model or os.getenv("AIPLAT_PI_MODEL") or "").strip()
    cwd = resolve_coding_cwd(preferred_cwd)
    run_coding_exec = _load_run_coding_exec()
    # Bridge already applied sandbox policy; coding_exec still gates host cwd.
    result = run_coding_exec(
        cwd=cwd,
        prompt=prompt,
        model=model_s,
        allow_host=True,
        timeout_sec=int(timeout_sec),
    )
    out: Dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "text": str(result.get("text") or ""),
        "cwd": str(result.get("cwd") or cwd),
        "model": str(result.get("model") or model_s),
        "executor": str(result.get("executor") or "pi_print"),
        "experiment": "factory_in_way4",
        "skipped": False,
    }
    err = result.get("error")
    if err:
        out["error"] = str(err)
    elif not out["ok"] and not out["text"]:
        out["error"] = "pi coding exec failed"
    return out
