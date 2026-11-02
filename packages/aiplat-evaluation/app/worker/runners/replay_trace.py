"""replay_trace — readonly replay of payload.trace (no LLM / no tools).

Honesty: P1 pass/steps/latency are engineering scores; accuracy_claim=false.
"""
from __future__ import annotations

from typing import Any, Dict

from app.scoring.semantics import replay_trace_p1_metrics
from app.worker.runners._common import runner_result


def run_replay_trace(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    trace = payload.get("trace")
    expected = payload.get("expected")
    job_id = str(job.get("job_id") or "")
    has_trace = isinstance(trace, dict)
    ok = has_trace
    if has_trace and isinstance(expected, dict) and "ok" in expected and "ok" in trace:
        ok = expected.get("ok") == trace.get("ok")
    steps = 0
    duration_ms = 0.0
    if has_trace:
        if isinstance(trace.get("steps"), list):
            steps = len(trace["steps"])
        for key in ("duration_ms", "latency_ms", "elapsed_ms"):
            if key in trace:
                try:
                    duration_ms = float(trace.get(key) or 0)
                except (TypeError, ValueError):
                    duration_ms = 0.0
                break
    return runner_result(
        runner_id="replay_trace",
        job_id=job_id,
        ok=ok,
        metrics=replay_trace_p1_metrics(steps=steps, ok=ok, duration_ms=duration_ms),
        evidence={"trace_present": has_trace},
        detail="" if ok else "missing or mismatched trace",
    )
