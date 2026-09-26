"""Org L5 Phase 3 — organization memory (run digests + exception jurisprudence).

Local JSONL under AIPLAT_HOME/org/memory.jsonl. Optional best-effort mirror into
OntologyCaseStore (no TBox evolve / no EDGE_AUTO_APPLY).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _memory_path() -> Path:
    d = _home() / "org"
    d.mkdir(parents=True, exist_ok=True)
    return d / "memory.jsonl"


def _outcome_for_status(status: str) -> str:
    st = (status or "").lower()
    if st in ("succeeded", "completed", "approved_dry"):
        return "success"
    if st in ("needs_hitl", "completed_partial"):
        return "partial"
    if st in ("failed", "cancelled"):
        return "failure"
    return "partial"


def record_run_memory(run: Dict[str, Any]) -> Dict[str, Any]:
    """Append OrgRun digest; best-effort case-store mirror (never mutates TBox)."""
    if not isinstance(run, dict) or not run.get("run_id"):
        return {"status": "skip", "reason": "no_run"}

    reasons = []
    for e in run.get("exceptions") or []:
        if isinstance(e, dict) and e.get("reason"):
            reasons.append(str(e.get("reason")))

    entry = {
        "kind": "org_run",
        "run_id": run.get("run_id"),
        "goal_id": run.get("goal_id"),
        "domain_id": run.get("domain_id"),
        "week_label": run.get("week_label") or "",
        "status": run.get("status"),
        "exception_reasons": reasons,
        "metrics_partial": run.get("metrics_partial") or {},
        "summary": (
            f"OrgRun {run.get('run_id')} status={run.get('status')} "
            f"exceptions={','.join(reasons) or 'none'}"
        )[:500],
        "created_at": time.time(),
        "authority_note": "org memory only; no TBox evolve",
    }

    path = _memory_path()
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("org memory append failed", exc_info=True)
        return {"status": "error", "run_id": run.get("run_id")}

    case_id = ""
    try:
        from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

        store = OntologyCaseStore(str(run.get("domain_id") or "it-ops"))
        tags = ["org_l5", "org_run"]
        if run.get("week_label"):
            tags.append(f"week:{run.get('week_label')}")
        for r in reasons[:3]:
            tags.append(f"exc:{r}")
        rec = store.record(
            title=f"OrgRun {run.get('run_id')}",
            summary=entry["summary"],
            outcome=_outcome_for_status(str(run.get("status") or "")),
            reward=0.55 if entry["status"] in ("succeeded", "completed") else 0.4,
            action_id="org_run",
            entity_id=str(run.get("run_id") or ""),
            tags=tags,
            metadata={
                "goal_id": run.get("goal_id"),
                "week_label": run.get("week_label"),
                "exception_reasons": reasons,
            },
            case_id=f"org-run-{run.get('run_id')}",
            write_graph=False,
        )
        case_id = str(rec.get("case_id") or "")
    except Exception:
        logger.debug("org→case mirror skipped", exc_info=True)

    return {
        "status": "ok",
        "run_id": run.get("run_id"),
        "case_id": case_id,
        "path": str(path),
    }


def list_memory(limit: int = 50, domain_id: str = "") -> Dict[str, Any]:
    path = _memory_path()
    rows: List[Dict[str, Any]] = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if domain_id and row.get("domain_id") != domain_id:
                    continue
                rows.append(row)
                if len(rows) >= max(1, min(int(limit), 200)):
                    break
        except Exception:
            logger.warning("org memory list failed", exc_info=True)
    return {"items": rows, "count": len(rows)}


def search_exceptions(query: str = "", *, domain_id: str = "", limit: int = 20) -> Dict[str, Any]:
    """Search exception jurisprudence by reason / summary keyword."""
    q = (query or "").strip().lower()
    items = list_memory(limit=200, domain_id=domain_id).get("items") or []
    hits: List[Dict[str, Any]] = []
    for row in items:
        reasons = [str(r).lower() for r in (row.get("exception_reasons") or [])]
        blob = " ".join(reasons + [str(row.get("summary") or "").lower(), str(row.get("status") or "")])
        if q and q not in blob:
            continue
        if not reasons and q and "hitl" not in blob:
            continue
        hits.append(
            {
                "run_id": row.get("run_id"),
                "goal_id": row.get("goal_id"),
                "domain_id": row.get("domain_id"),
                "week_label": row.get("week_label"),
                "status": row.get("status"),
                "exception_reasons": row.get("exception_reasons") or [],
                "summary": row.get("summary"),
                "created_at": row.get("created_at"),
            }
        )
        if len(hits) >= max(1, min(int(limit), 50)):
            break
    return {
        "query": query,
        "hits": hits,
        "count": len(hits),
        "authority_note": "org exception jurisprudence; suggestion layer only; no auto TBox",
    }
