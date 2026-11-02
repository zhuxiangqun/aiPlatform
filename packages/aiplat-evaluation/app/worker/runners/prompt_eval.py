"""prompt_eval — pure-text local deterministic scorer (LLM optional later).

Honesty: default mode does not call Central or tools. Live infra ModelManager
path is gated by AIPLAT_EVAL_LLM=1 in a later wiring; local tests stay offline.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from app.worker.runners._common import runner_result


def run_prompt_eval(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_id = str(job.get("job_id") or "")
    prompt = str(payload.get("prompt") or payload.get("input") or "")
    expected = str(payload.get("expected") or payload.get("expected_text") or "")
    # Optional stub "model" output for local engineering without provider.
    actual = str(payload.get("actual") or payload.get("output") or "")
    if not actual and expected:
        # Deterministic stand-in: treat expected as gold; score exact match only
        # when caller supplies actual. Without actual → fail closed (not fake pass).
        return runner_result(
            runner_id="prompt_eval",
            job_id=job_id,
            ok=False,
            metrics={"pass": 0.0, "exact_match": 0.0},
            evidence={"prompt_len": len(prompt), "has_actual": False},
            detail="prompt_eval requires payload.actual (or AIPLAT_EVAL_LLM later)",
            mode="local_deterministic",
        )
    exact = 1.0 if (actual == expected and expected != "") else 0.0
    if expected == "" and actual != "":
        # No gold: record length only; ok=True only if non-empty output (engineering)
        exact = 0.0
        ok = bool(actual.strip())
    else:
        ok = exact == 1.0
    _ = os.getenv("AIPLAT_EVAL_LLM")  # reserved; no provider call in this slice
    return runner_result(
        runner_id="prompt_eval",
        job_id=job_id,
        ok=ok,
        metrics={"pass": 1.0 if ok else 0.0, "exact_match": exact},
        evidence={"prompt_len": len(prompt), "actual_len": len(actual)},
        detail="" if ok else "exact_match failed or empty",
        mode="local_deterministic",
    )
