"""self_learn — P2-3 self-learning resistance baseline v0.

Honesty: in-process policy sim; accuracy_claim=false;
pack writeback_authorized must remain false.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.scoring.self_learn import KINDS, score_case, score_pack
from app.worker.runners._common import runner_result


def run_self_learn(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_id = str(job.get("job_id") or "")
    pack_id = str(payload.get("pack_id") or payload.get("schema") or "self_learn.v0")
    pack_meta = {
        "writeback_authorized": bool(payload.get("writeback_authorized", False)),
        "calibration_disagree_rate": payload.get("calibration_disagree_rate"),
    }
    cases_raw = payload.get("cases")
    if isinstance(cases_raw, list) and cases_raw:
        cases: List[Dict[str, Any]] = [dict(c) for c in cases_raw if isinstance(c, dict)]
        dim = score_pack(cases, pack_id=pack_id, pack_meta=pack_meta)
        per = [score_case(c, pack_meta=pack_meta) for c in cases]
        ok = bool(dim.get("self_learn_pass"))
        return runner_result(
            runner_id="self_learn",
            job_id=job_id,
            ok=ok,
            metrics={
                "cases_n": float(dim.get("cases_n") or 0),
                "cases_ok": float(dim.get("cases_ok") or 0),
                "case_pass_rate": float(dim.get("case_pass_rate") or 0.0),
                "self_learn_pass": 1.0 if ok else 0.0,
                "writeback_authorized": 1.0 if pack_meta["writeback_authorized"] else 0.0,
            },
            evidence={
                "pack_id": pack_id,
                "kinds_required": list(KINDS),
                "kinds_seen": dim.get("kinds_seen"),
                "kinds_missing": dim.get("kinds_missing"),
                "cases": per,
                "self_learn_dimension": dim,
            },
            detail="self_learn pack" if ok else f"self_learn fail missing={dim.get('kinds_missing')}",
            mode="self_learn_v0",
        )

    case = dict(payload)
    if "kind" not in case and isinstance(payload.get("case"), dict):
        case = dict(payload["case"])
    scored = score_case(case, pack_meta=pack_meta)
    ok_case = bool(scored.get("ok"))
    return runner_result(
        runner_id="self_learn",
        job_id=job_id,
        ok=ok_case,
        metrics={
            "cases_n": 1.0,
            "cases_ok": 1.0 if ok_case else 0.0,
            "case_pass_rate": 1.0 if ok_case else 0.0,
            "self_learn_pass": 1.0 if ok_case else 0.0,
        },
        evidence={"case": scored, "single_case": True},
        detail="self_learn case" if ok_case else "self_learn case fail",
        mode="self_learn_v0",
    )
