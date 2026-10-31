"""Live drill evidence helpers for authorize hard gates.

Does not authorize. Authorize scripts must refuse without a
production_signed live-*.json under the track drills dir.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def summarize_live_drills(drill_dir: Path) -> dict[str, Any]:
    """Return latest live-*.json summary for a track."""
    out: dict[str, Any] = {
        "drill_dir": str(drill_dir),
        "live_count": 0,
        "latest": None,
        "production_signed": False,
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
    out["production_signed"] = bool(data.get("production_signed"))
    out["kind"] = data.get("kind")
    out["drill_id"] = data.get("drill_id")
    out["environment"] = data.get("environment")
    # Convenience: any signed file exists (status only; authorize still uses latest).
    signed_any = False
    for p in lives:
        try:
            if bool(json.loads(p.read_text(encoding="utf-8")).get("production_signed")):
                signed_any = True
                break
        except (OSError, json.JSONDecodeError):
            continue
    out["any_production_signed"] = signed_any
    return out


def require_signed_live(drill_dir: Path) -> tuple[bool, dict[str, Any]]:
    """True iff the newest live-*.json has production_signed=true."""
    summary = summarize_live_drills(drill_dir)
    return bool(summary.get("production_signed")), summary
