"""Novel gold findings → experience_feedback pending (no platform import).

Writes compatible JSON rows to AIPLAT_EXPERIENCE_FILE (or ~/.aiplat/experience_feedback.json).
Promotion → Team Brain stays in platform ExperienceStore._promote.
Does **not** rewrite gold cases.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

logger = logging.getLogger(__name__)


def _experience_path() -> str:
    env = (os.environ.get("AIPLAT_EXPERIENCE_FILE") or "").strip()
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    return os.path.join(home, "experience_feedback.json")


def _safe(s: str) -> str:
    out = []
    for ch in (s or "")[:80]:
        if ch.isalnum() or ch in "-_.":
            out.append(ch.lower())
        else:
            out.append("_")
    return "".join(out) or "x"


def register_novel_as_experience(
    novels: Sequence[Dict[str, Any]],
    *,
    source: str = "code_review_gold",
) -> List[Dict[str, Any]]:
    """Append novel P0/P1 as pending experience gotchas (idempotent by rule_id)."""
    recorded: List[Dict[str, Any]] = []
    if not novels:
        return recorded
    path = _experience_path()
    try:
        rows: List[Dict[str, Any]] = []
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            rows = data if isinstance(data, list) else []
    except Exception as e:
        logger.debug("experience load skipped: %s", e, exc_info=True)
        rows = []

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for n in list(novels)[:20]:
        if not isinstance(n, dict):
            continue
        sev = str(n.get("severity") or "P1").upper()
        case_id = _safe(str(n.get("case_id") or "case"))
        file_id = _safe(str(n.get("file") or "file"))
        rule_id = f"review-novel-{case_id}-{file_id}-{sev.lower()}"
        content = str(n.get("description") or n.get("title") or rule_id)[:500]
        risk = "high" if sev == "P0" else "low"
        existing = next(
            (r for r in rows if r.get("rule_id") == rule_id and r.get("status") == "pending"),
            None,
        )
        if existing:
            existing["occurrences"] = int(existing.get("occurrences") or 1) + 1
            existing["updated_at"] = now
            sources = existing.get("sources") or [existing.get("source") or source]
            if source not in sources:
                sources.append(source)
            existing["sources"] = sources
            recorded.append({"rule_id": rule_id, "merged": True, "id": existing.get("id")})
            continue
        rec = {
            "id": f"exp-novel-{int(time.time() * 1000)}-{file_id}",
            "rule_id": rule_id,
            "content": content,
            "source": source,
            "sources": [source],
            "confidence": 0.85,
            "risk": risk,
            "status": "pending",
            "verify_count": 0,
            "verify_events": [],
            "occurrences": 1,
            "require_review": sev == "P0",
            "created_at": now,
            "updated_at": now,
            "meta": {
                "kind": "novel_candidate",
                "severity": sev,
                "file": n.get("file"),
                "case_id": n.get("case_id"),
            },
        }
        rows.append(rec)
        recorded.append({"rule_id": rule_id, "merged": False, "id": rec["id"], "risk": risk})

    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        logger.debug("experience save skipped: %s", e, exc_info=True)
        return []
    return recorded
