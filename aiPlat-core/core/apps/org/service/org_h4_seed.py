"""S1 — ensure sandbox approval_rules seed when missing."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _seed_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "org"
        / "approval_rules.yaml"
    )


def ensure_approval_rules_seed() -> Dict[str, Any]:
    """Copy seed only when AIPLAT_HOME/org/approval_rules.yaml is absent."""
    dest = _home() / "org" / "approval_rules.yaml"
    if dest.is_file():
        return {"status": "exists", "path": str(dest)}
    src = _seed_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return {"status": "installed", "path": str(dest), "from": str(src)}
    rules = {
        "enabled": True,
        "sandbox_only": True,
        "confidence_min": 0.95,
        "domains": ["it-ops"],
        "exact_strategies": ["exact"],
        "daily_auto_rate_max": 0.2,
        "min_sample": 5,
        "circuit_reason": "",
        "circuit_at": 0,
    }
    dest.write_text(yaml.safe_dump(rules, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"status": "installed_default", "path": str(dest)}
