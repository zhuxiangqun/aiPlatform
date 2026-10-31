"""Write environment=local drill evidence (never production_signed / authorize)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def write_local_drill(
    *,
    out_path: Path,
    kind: str,
    schema_version: str,
    drill_id: str,
    operator: str,
    items: Dict[str, Any],
    limitations: List[str],
    note: str,
    authorize_flag_key: str,
    local_sign: bool = False,
) -> Dict[str, Any]:
    """Write local-*.json. production_signed always False."""
    merged = dict(items)
    items_file = (os.environ.get("AIPLAT_LOCAL_DRILL_ITEMS_FILE") or "").strip()
    if items_file and Path(items_file).is_file():
        merged.update(json.loads(Path(items_file).read_text(encoding="utf-8")))

    signed = bool(local_sign)
    if signed:
        for _k, v in merged.items():
            if not (
                isinstance(v, dict)
                and v.get("done")
                and str(v.get("evidence") or "").strip()
            ):
                signed = False
                break

    out = {
        "kind": kind,
        "schema_version": schema_version,
        "drill_id": drill_id,
        "environment": "local",
        "operator": operator,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "production_signed": False,
        "local_signed": signed,
        "items": merged,
        "limitations": limitations,
        "note": note,
        authorize_flag_key: True,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def latest_local(drill_dir: Path) -> Optional[Path]:
    files = list(drill_dir.glob("local-*.json"))
    if not files:
        return None
    files.sort(key=lambda p: (p.stat().st_mtime_ns, p.name))
    return files[-1]


def summarize_local(drill_dir: Path) -> Dict[str, Any]:
    latest = latest_local(drill_dir)
    out: Dict[str, Any] = {
        "drill_dir": str(drill_dir),
        "local_count": len(list(drill_dir.glob("local-*.json"))) if drill_dir.is_dir() else 0,
        "latest": str(latest) if latest else None,
        "local_signed": False,
        "production_signed": False,
        "environment": None,
    }
    if not latest:
        return out
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        out["parse_error"] = True
        return out
    out["local_signed"] = bool(data.get("local_signed"))
    out["production_signed"] = bool(data.get("production_signed"))
    out["environment"] = data.get("environment")
    out["drill_id"] = data.get("drill_id")
    out["kind"] = data.get("kind")
    return out
