"""V1 — read-only five-step replay. Missing steps stay missing.

Does not write ontology YAML, edges, runs, cases, proposals, signals, or tickets.
May append one audit read line. That line is not a business step.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_ABSENT = "该步未发生"


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _match(rows: List[Dict[str, Any]], trace_id: str) -> List[Dict[str, Any]]:
    return [row for row in rows if str(row.get("trace_id") or "") == trace_id]


def _step(name: str, *, status: str, records: List[Dict[str, Any]], reason: str = "") -> Dict[str, Any]:
    note = _ABSENT if status == "absent" else ""
    if status == "conflict" and not reason:
        reason = "conflict"
    return {
        "step": name,
        "status": status,
        "note": note,
        "reason": reason,
        "records": records,
    }


def _audit(trace_id: str, status: str) -> None:
    try:
        path = _home() / "k_wave" / "trace_replay_reads.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {
            "kind": "trace_replay_read",
            "trace_id": trace_id,
            "status": status,
            "at": time.time(),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        logger.debug("trace replay audit skipped", exc_info=True)


def replay_org_trace(trace_id: str = "", *, domain_id: str = "it-ops") -> Dict[str, Any]:
    """Assemble one chain by exact trace_id. Never stitches by time or name."""
    tid = (trace_id or "").strip()
    if not tid:
        return {"status": "invalid", "reason": "trace_id_required", "read_only": True, "steps": []}

    did = (domain_id or "").strip() or "it-ops"
    from core.apps.fde.service.k_wave_arbit import tickets_path
    from core.apps.fde.service.k_wave_propose import ledger_path
    from core.apps.fde.service.k_wave_signal import signals_path
    from core.harness.knowledge.ontology_case_learning import OntologyCaseStore

    signals = _match(_jsonl(signals_path()), tid)
    tickets = _match(_jsonl(tickets_path()), tid)
    runs_path = _home() / "org" / "runs.json"
    runs_doc = {}
    if runs_path.is_file():
        try:
            runs_doc = json.loads(runs_path.read_text(encoding="utf-8"))
        except Exception:
            runs_doc = {}
    runs = _match(list(runs_doc.get("runs") or []) if isinstance(runs_doc, dict) else [], tid)
    cases = []
    for case in OntologyCaseStore(did)._load().values():
        meta = case.metadata if isinstance(case.metadata, dict) else {}
        if str(meta.get("trace_id") or "") == tid:
            cases.append(
                {
                    "case_id": case.case_id,
                    "trace_id": tid,
                    "trace_origin": str(meta.get("trace_origin") or ""),
                    "outcome": case.outcome,
                    "action_id": case.action_id,
                    "schema_gap": case.outcome == "failure" or bool(meta.get("schema_gap")),
                    "gap_note": str(meta.get("gap_note") or ""),
                    "proposal_id": case.proposal_id,
                }
            )
    proposals = _match(_jsonl(ledger_path()), tid)

    extraction_recs = [
        {
            "signal_id": row.get("signal_id"),
            "trace_id": tid,
            "trace_origin": row.get("trace_origin"),
        }
        for row in signals
        if row.get("trace_origin") == "extraction_confirm"
    ]
    bad_signals = [row for row in signals if row.get("trace_origin") != "extraction_confirm"]

    run_recs = [
        {
            "run_id": row.get("run_id"),
            "trace_id": tid,
            "trace_origin": row.get("trace_origin"),
            "status": row.get("status"),
        }
        for row in runs
    ]
    ticket_recs = [
        {
            "ticket_id": row.get("ticket_id"),
            "trace_id": tid,
            "trace_origin": row.get("trace_origin"),
            "status": row.get("status"),
        }
        for row in tickets
    ]
    proposal_recs = [
        {
            "proposal_id": row.get("proposal_id"),
            "trace_id": tid,
            "trace_origin": row.get("trace_origin") or "",
            "auto_apply": row.get("auto_apply"),
            "status": row.get("status"),
        }
        for row in proposals
    ]

    parent = bool(extraction_recs) or any(row.get("trace_origin") == "run" for row in runs)
    direct_run = any(
        row.get("trace_origin") == "run" and str(row.get("run_id") or "") == tid
        for row in runs
    )

    def _present(records: List[Dict[str, Any]], reason: str = "") -> Dict[str, str]:
        if reason:
            return {"status": "conflict", "reason": reason}
        if records:
            return {"status": "present", "reason": ""}
        return {"status": "absent", "reason": ""}

    extraction_reason = "extraction_origin" if bad_signals else ""
    run_reason = "run_backfill_forbidden" if extraction_recs and direct_run else ""
    ticket_reason = (
        "inherited_without_parent"
        if any(row.get("trace_origin") == "inherited" and not parent for row in ticket_recs)
        else ""
    )
    case_reason = (
        "inherited_without_parent"
        if any(row.get("trace_origin") == "inherited" and not parent for row in cases)
        else ""
    )
    proposal_reason = ""
    if any(row.get("auto_apply") is True for row in proposal_recs):
        proposal_reason = "auto_apply_not_false"
    elif any(row.get("trace_origin") == "inherited" and not parent for row in proposal_recs):
        proposal_reason = "inherited_without_parent"

    extraction_s = _present(extraction_recs, extraction_reason)
    arbitration_s = _present(ticket_recs, ticket_reason)
    run_s = _present(run_recs, run_reason)
    case_s = _present(cases, case_reason)
    proposal_s = _present(proposal_recs, proposal_reason)
    steps = [
        _step("extraction_confirm", status=extraction_s["status"], records=extraction_recs, reason=extraction_s["reason"]),
        _step("arbitration", status=arbitration_s["status"], records=ticket_recs, reason=arbitration_s["reason"]),
        _step("run", status=run_s["status"], records=run_recs, reason=run_s["reason"]),
        _step("case", status=case_s["status"], records=cases, reason=case_s["reason"]),
        _step("proposal", status=proposal_s["status"], records=proposal_recs, reason=proposal_s["reason"]),
    ]
    conflicts = [s["reason"] for s in steps if s["reason"]]
    status = "conflict" if conflicts else "ok"
    out = {
        "status": status,
        "trace_id": tid,
        "domain_id": did,
        "read_only": True,
        "conflicts": conflicts,
        "steps": steps,
        "schema_gaps": [c for c in cases if c.get("schema_gap")],
        "wrote_live_yaml": False,
        "authority_note": "V1 replay is evidence only; absent means 该步未发生; gap probe does not write YAML; not M4",
    }
    _audit(tid, status)
    return out
