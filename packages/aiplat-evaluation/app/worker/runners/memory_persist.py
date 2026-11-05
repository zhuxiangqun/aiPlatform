"""memory_persist — P2-2 persistent memory baseline v0.

Honesty: in-process fixture store; accuracy_claim=false;
≠ production MemoryManager; ≠ vector-IR accuracy.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.scoring.memory_persist import KINDS, score_case, score_pack
from app.worker.runners._common import runner_result


def run_memory_persist(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_id = str(job.get("job_id") or "")
    pack_id = str(payload.get("pack_id") or payload.get("schema") or "memory_persist.v0")
    cases_raw = payload.get("cases")
    if isinstance(cases_raw, list) and cases_raw:
        cases: List[Dict[str, Any]] = [dict(c) for c in cases_raw if isinstance(c, dict)]
        dim = score_pack(cases, pack_id=pack_id)
        per = [score_case(c) for c in cases]
        ok = bool(dim.get("memory_pass"))
        return runner_result(
            runner_id="memory_persist",
            job_id=job_id,
            ok=ok,
            metrics={
                "cases_n": float(dim.get("cases_n") or 0),
                "cases_ok": float(dim.get("cases_ok") or 0),
                "case_pass_rate": float(dim.get("case_pass_rate") or 0.0),
                "memory_pass": 1.0 if ok else 0.0,
            },
            evidence={
                "pack_id": pack_id,
                "kinds_required": list(KINDS),
                "kinds_seen": dim.get("kinds_seen"),
                "kinds_missing": dim.get("kinds_missing"),
                "cases": per,
                "memory_dimension": dim,
            },
            detail="memory_persist pack" if ok else f"memory_persist fail missing={dim.get('kinds_missing')}",
            mode="memory_persist_v0",
        )

    case = dict(payload)
    if "kind" not in case and isinstance(payload.get("case"), dict):
        case = dict(payload["case"])
    scored = score_case(case)
    dim = score_pack([case], pack_id=pack_id)
    ok_case = bool(scored.get("ok"))
    return runner_result(
        runner_id="memory_persist",
        job_id=job_id,
        ok=ok_case,
        metrics={
            "cases_n": 1.0,
            "cases_ok": 1.0 if ok_case else 0.0,
            "case_pass_rate": 1.0 if ok_case else 0.0,
            "memory_pass": 1.0 if ok_case else 0.0,
        },
        evidence={"case": scored, "memory_dimension": dim, "single_case": True},
        detail="memory_persist case" if ok_case else "memory_persist case fail",
        mode="memory_persist_v0",
    )
