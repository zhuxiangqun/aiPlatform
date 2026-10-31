"""Live drill evidence helpers for authorize hard gates.

Does not authorize. Authorize scripts must refuse without a
production_signed live-*.json under the track drills dir, with a
production-class environment (staging / prod-canary).

local-*.json and environment=local are engineering-only — never authorize.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Authorize only accepts these environments on live-*.json.
PRODUCTION_CLASS_ENVS = frozenset({"staging", "prod-canary"})
# Explicitly non-authorize (local staging / scaffold / lab).
NON_AUTHORIZE_ENVS = frozenset(
    {"scaffold", "local", "temp", "tmp", "docker-ephemeral", "lab", "local-staging"}
)


def _env_ok_for_authorize(env: str) -> bool:
    e = (env or "").strip().lower()
    return e in PRODUCTION_CLASS_ENVS


def summarize_live_drills(drill_dir: Path) -> dict[str, Any]:
    """Return latest live-*.json summary for a track (ignores local-*.json)."""
    out: dict[str, Any] = {
        "drill_dir": str(drill_dir),
        "live_count": 0,
        "latest": None,
        "production_signed": False,
        "environment_ok_for_authorize": False,
        "required_for_authorize": True,
    }
    if not drill_dir.is_dir():
        return out
    lives = list(drill_dir.glob("live-*.json"))
    out["live_count"] = len(lives)
    if not lives:
        return out
    # Prefer mtime, then name — authorize must see the newest record.
    lives.sort(key=lambda p: (p.stat().st_mtime_ns, p.name))
    latest = lives[-1]
    out["latest"] = str(latest)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        out["parse_error"] = True
        return out
    env = str(data.get("environment") or "")
    out["kind"] = data.get("kind")
    out["drill_id"] = data.get("drill_id")
    out["environment"] = env
    out["environment_ok_for_authorize"] = _env_ok_for_authorize(env)
    # production_signed alone is insufficient if env is local/scaffold.
    raw_signed = bool(data.get("production_signed"))
    out["production_signed_raw"] = raw_signed
    out["production_signed"] = bool(raw_signed and out["environment_ok_for_authorize"])
    if raw_signed and not out["environment_ok_for_authorize"]:
        out["refuse_reason"] = "non_production_class_environment"
    # Convenience: any signed+env-ok file exists (status only; authorize still uses latest).
    signed_any = False
    for p in lives:
        try:
            row = json.loads(p.read_text(encoding="utf-8"))
            if bool(row.get("production_signed")) and _env_ok_for_authorize(
                str(row.get("environment") or "")
            ):
                signed_any = True
                break
        except (OSError, json.JSONDecodeError):
            continue
    out["any_production_signed"] = signed_any
    return out


def require_signed_live(drill_dir: Path) -> tuple[bool, dict[str, Any]]:
    """True iff newest live-*.json is production_signed and env is staging/prod-canary."""
    summary = summarize_live_drills(drill_dir)
    return bool(summary.get("production_signed")), summary
