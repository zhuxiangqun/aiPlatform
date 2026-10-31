"""Validate / optionally sign live drill evidence.

Signing sets production_signed=true only when every items[*].done
is true and evidence is non-empty. Never touches checklists or authorize.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _item_ok(v: Any) -> bool:
    if not isinstance(v, dict):
        return False
    if not bool(v.get("done")):
        return False
    ev = v.get("evidence", "")
    return isinstance(ev, str) and bool(ev.strip())


def validate_live_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") or {}
    missing: list[str] = []
    for key, val in items.items():
        if not _item_ok(val):
            missing.append(key)
    env = str(data.get("environment") or "")
    scaffoldish = env.lower() in {
        "scaffold",
        "local",
        "temp",
        "tmp",
        "docker-ephemeral",
        "lab",
    }
    return {
        "path": str(path),
        "drill_id": data.get("drill_id"),
        "environment": env,
        "scaffoldish_environment": scaffoldish,
        "production_signed": bool(data.get("production_signed")),
        "items_complete": len(missing) == 0 and bool(items),
        "missing_or_incomplete_items": missing,
        "item_keys": sorted(items.keys()),
    }


def sign_live_file(path: Path, *, allow_scaffold_env: bool = False) -> dict[str, Any]:
    """Set production_signed=true if items complete; else refuse."""
    report = validate_live_file(path)
    if report["scaffoldish_environment"] and not allow_scaffold_env:
        report["signed"] = False
        report["refused"] = "scaffoldish_environment"
        return report
    if not report["items_complete"]:
        report["signed"] = False
        report["refused"] = "items_incomplete"
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    data["production_signed"] = True
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["production_signed"] = True
    report["signed"] = True
    report["refused"] = None
    return report
