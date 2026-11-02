"""replay_trace — readonly replay of payload.trace (no LLM / no tools)."""
from __future__ import annotations

from typing import Any, Dict

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
    if has_trace and isinstance(trace.get("steps"), list):
        steps = len(trace["steps"])
    return runner_result(
        runner_id="replay_trace",
        job_id=job_id,
        ok=ok,
        metrics={"steps": steps, "pass": 1.0 if ok else 0.0},
        evidence={"trace_present": has_trace},
        detail="" if ok else "missing or mismatched trace",
    )
