"""Weekly KB health markdown archive (HYBRID_ENTERPRISE_KB_HEALTH §4.2 / §6.1).

Writes ``kb-health-{YYYY-WW}.md`` under a governance reports directory.
Cron is opt-in via ``AIPLAT_KB_HEALTH_ARCHIVE_HOURS`` (default 168; ``0`` = off).
"""
from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def reports_dir() -> Path:
    raw = (os.getenv("AIPLAT_KB_HEALTH_REPORT_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    home = (
        os.getenv("AIPLAT_PLATFORM_HOME")
        or os.getenv("AIPLAT_HOME")
        or str(Path(get_aiplat_home()))
    )
    return Path(home).expanduser() / "governance" / "reports"


def iso_week_tag(now: Optional[datetime] = None) -> str:
    dt = now or datetime.now(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def archive_filename(week: Optional[str] = None) -> str:
    return f"kb-health-{week or iso_week_tag()}.md"


def archive_kb_health_report(
    *,
    tenant_id: str = "default",
    collection_id: str = "default",
    window_hours: int = 168,
    project_id: str = "",
    force: bool = False,
    week: Optional[str] = None,
) -> Dict[str, Any]:
    """Build live KB health markdown and persist under reports_dir().

    Skips rewrite when the week file already exists unless ``force``.
    """
    from delivery.kb_health import build_kb_health_report, render_kb_health_markdown

    tag = week or iso_week_tag()
    out_dir = reports_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / archive_filename(tag)
    if path.is_file() and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_archived",
            "week": tag,
            "path": str(path),
        }

    report = build_kb_health_report(
        tenant_id=tenant_id,
        collection_id=collection_id,
        window_hours=window_hours,
        project_id=project_id,
    )
    body = render_kb_health_markdown(report)
    header = (
        f"<!-- archived_at={datetime.now(timezone.utc).isoformat()} "
        f"week={tag} tenant={tenant_id} collection={collection_id} -->\n"
    )
    path.write_text(header + body, encoding="utf-8")
    return {
        "ok": True,
        "skipped": False,
        "week": tag,
        "path": str(path),
        "bytes": path.stat().st_size,
        "health_score": (report.get("health") or {}).get("score"),
    }


def list_kb_health_archives(limit: int = 52) -> Dict[str, Any]:
    d = reports_dir()
    if not d.is_dir():
        return {"ok": True, "items": [], "dir": str(d)}
    files = sorted(d.glob("kb-health-*.md"), key=lambda p: p.name, reverse=True)
    items: List[Dict[str, Any]] = []
    for p in files[: max(1, min(int(limit or 52), 200))]:
        items.append(
            {
                "name": p.name,
                "week": p.stem.replace("kb-health-", "", 1),
                "path": str(p),
                "bytes": p.stat().st_size,
                "mtime": datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return {"ok": True, "items": items, "dir": str(d)}


def read_kb_health_archive(week: str) -> Dict[str, Any]:
    tag = str(week or "").strip()
    if not tag:
        return {"ok": False, "error": "week_required"}
    # Accept bare W or full YYYY-WW
    if tag.upper().startswith("W") and "-" not in tag:
        tag = f"{datetime.now(timezone.utc).isocalendar().year}-{tag.upper()}"
    path = reports_dir() / archive_filename(tag)
    if not path.is_file():
        return {"ok": False, "error": "not_found", "week": tag, "path": str(path)}
    return {
        "ok": True,
        "week": tag,
        "path": str(path),
        "markdown": path.read_text(encoding="utf-8"),
    }


def archive_interval_hours() -> float:
    raw = (os.getenv("AIPLAT_KB_HEALTH_ARCHIVE_HOURS", "168") or "168").strip()
    try:
        return float(raw)
    except ValueError:
        return 168.0
