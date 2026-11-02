"""arena — pure-text pairwise compare only (tools → sandbox_required)."""
from __future__ import annotations

from typing import Any, Dict

from app.worker.runners._common import runner_result


def run_arena(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_id = str(job.get("job_id") or "")
    # Tooling flag fail-closed for B2.
    if payload.get("tools") or payload.get("use_tools") or payload.get("tool_calls"):
        raise ValueError("sandbox_required:arena")
    a = str(payload.get("response_a") or payload.get("a") or "")
    b = str(payload.get("response_b") or payload.get("b") or "")
    prefer = str(payload.get("prefer") or payload.get("expected_winner") or "").lower()
    if not a or not b:
        return runner_result(
            runner_id="arena",
            job_id=job_id,
            ok=False,
            metrics={"pass": 0.0},
            evidence={},
            detail="arena requires response_a and response_b",
        )
    # Deterministic length heuristic (engineering only; accuracy_claim=false).
    winner = "a" if len(a) >= len(b) else "b"
    ok = True
    if prefer in {"a", "b"}:
        ok = winner == prefer
    return runner_result(
        runner_id="arena",
        job_id=job_id,
        ok=ok,
        metrics={
            "pass": 1.0 if ok else 0.0,
            "winner": winner,
            "len_a": len(a),
            "len_b": len(b),
        },
        evidence={"pure_text": True},
        detail="" if ok else f"winner={winner} prefer={prefer}",
    )
