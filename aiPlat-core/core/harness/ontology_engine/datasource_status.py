"""
Data Source Status — sync monitoring and health dashboard for enterprise connectors.

Phase D: Provides a unified view of all registered data sources:
  - Which sources synced successfully vs failed
  - Last sync timestamps and row counts
  - Error summaries for troubleshooting
  - Simple status aggregator for the diagnostics dashboard

Usage:
    from core.harness.ontology_engine.datasource_status import get_sync_status
    status = get_sync_status()  # → {total, synced, failed, pending, per_source: [...]}
"""

from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml as _yaml

logger = __import__("logging").getLogger(__name__)


@dataclass
class SourceStatus:
    name: str
    type: str  # "sql" | "api" | "file"
    status: str = "pending"  # "pending" | "syncing" | "synced" | "failed"
    last_sync_at: Optional[float] = None
    row_count: int = 0
    error: str = ""
    mapping_class: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "last_sync_at": self.last_sync_at,
            "row_count": self.row_count,
            "error": self.error,
            "mapping_class": self.mapping_class,
        }


_STATUS_FILE = Path(os.path.expanduser("~/.aiplat/datasources/.sync_status.json"))


def _load_sources() -> List[Dict[str, Any]]:
    """Load all registered datasource YAML files."""
    sources_dir = Path(os.path.expanduser("~/.aiplat/datasources"))
    if not sources_dir.is_dir():
        return []

    sources = []
    for yf in sources_dir.glob("*.yaml"):
        if yf.name.startswith("."):
            continue
        try:
            cfg = _yaml.safe_load(yf.read_text(encoding="utf-8"))
            if cfg and isinstance(cfg, dict) and cfg.get("name"):
                sources.append(cfg)
        except Exception:
            logger.debug("Failed to parse %s", yf)
    return sources


def get_sync_status() -> Dict[str, Any]:
    """Return unified sync status for all registered data sources.

    Used by the diagnostics dashboard to show connection health.
    """
    sources = _load_sources()
    history = {}
    if _STATUS_FILE.exists():
        try:
            history = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    total = len(sources)
    synced = 0
    failed = 0
    pending = 0
    per_source: List[Dict[str, Any]] = []

    for cfg in sources:
        name = cfg.get("name", "unknown")
        source_type = cfg.get("type", "sql")
        mapping = cfg.get("mapping", {})
        target_class = mapping.get("target_class", "") if isinstance(mapping, dict) else ""

        hist = history.get(name, {})
        status = hist.get("status", "pending")
        last_sync = hist.get("last_sync_at")
        rows = hist.get("row_count", 0)
        error = hist.get("error", "")

        if status == "synced":
            synced += 1
        elif status == "failed":
            failed += 1
        else:
            pending += 1

        per_source.append({
            "name": name,
            "type": source_type,
            "status": status,
            "last_sync_at": last_sync,
            "row_count": rows,
            "error": error,
            "mapping_class": target_class,
        })

    return {
        "total": total,
        "synced": synced,
        "failed": failed,
        "pending": pending,
        "per_source": per_source,
        "updated_at": time.time(),
    }


def record_sync_event(
    source_name: str,
    status: str,
    *,
    row_count: int = 0,
    error: str = "",
) -> None:
    """Record a sync event for a specific data source (best-effort, idempotent)."""
    history = {}
    if _STATUS_FILE.exists():
        try:
            history = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    history[source_name] = {
        "status": status,
        "last_sync_at": time.time(),
        "row_count": row_count,
        "error": error,
    }
    _STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATUS_FILE.write_text(json.dumps(history, indent=2))


def mark_all_pending() -> None:
    """Reset all sync statuses to pending (e.g. after config change or restart)."""
    _STATUS_FILE.unlink(missing_ok=True)


__all__ = ["SourceStatus", "get_sync_status", "record_sync_event", "mark_all_pending"]
