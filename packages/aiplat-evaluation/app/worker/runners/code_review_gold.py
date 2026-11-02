"""code_review_gold — static/semi-static gold match (no sandbox tools)."""
from __future__ import annotations

from typing import Any, Dict, List

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
            metrics={"pass": 0.0, "gold_n": 0, "findings_n": len(findings)},
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
        metrics={
            "pass": 1.0 if ok else 0.0,
            "gold_n": len(gold),
            "findings_n": len(findings),
        },
        evidence={"exact_set_match": ok},
        detail="" if ok else "findings != gold",
    )
