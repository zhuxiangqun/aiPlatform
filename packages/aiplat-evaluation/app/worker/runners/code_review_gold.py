"""code_review_gold — static/semi-static gold match (no sandbox tools).

Honesty: P1 exact_match/coverage are engineering scores; accuracy_claim=false.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.scoring.semantics import code_review_gold_p1_metrics
from app.worker.runners._common import runner_result


def run_code_review_gold(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_id = str(job.get("job_id") or "")
    findings: List[Any] = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    gold: List[Any] = payload.get("gold") if isinstance(payload.get("gold"), list) else []
    if not gold:
        return runner_result(
            runner_id="code_review_gold",
            job_id=job_id,
            ok=False,
            metrics=code_review_gold_p1_metrics(findings=findings, gold=[], ok=False),
            evidence={},
            detail="code_review_gold requires payload.gold",
        )
    # Exact set equality of stringified findings vs gold (engineering calibration).
    norm_f = sorted(str(x) for x in findings)
    norm_g = sorted(str(x) for x in gold)
    ok = norm_f == norm_g
    return runner_result(
        runner_id="code_review_gold",
        job_id=job_id,
        ok=ok,
        metrics=code_review_gold_p1_metrics(findings=findings, gold=gold, ok=ok),
        evidence={"exact_set_match": ok},
        detail="" if ok else "findings != gold",
    )
