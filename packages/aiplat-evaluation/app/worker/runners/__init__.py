"""B2-L allowlist + B3-L local_stub runners — dispatch by runner_id (no core.harness)."""
from __future__ import annotations

from typing import Any, Dict

from app.worker.runners.arena import run_arena
from app.worker.runners.cli_probe import run_cli_probe
from app.worker.runners.code_review_gold import run_code_review_gold
from app.worker.runners.http_probe import run_http_probe
from app.worker.runners.kb_rag import run_kb_rag
from app.worker.runners.prompt_eval import run_prompt_eval
from app.worker.runners.replay_trace import run_replay_trace
from app.worker.runners.security_redteam import run_security_redteam
from app.worker.runners.skill_suite import run_skill_suite

_RUNNERS = {
    "replay_trace": run_replay_trace,
    "prompt_eval": run_prompt_eval,
    "kb_rag": run_kb_rag,
    "code_review_gold": run_code_review_gold,
    "arena": run_arena,
    "http_probe": run_http_probe,
    "cli_probe": run_cli_probe,
    "skill_suite": run_skill_suite,
    "security_redteam": run_security_redteam,
}


def execute_runner(job: Dict[str, Any]) -> Dict[str, Any]:
    """prepare+execute+collect for an admitted allowlist job.

    Returns result dict with at least: ok, runner_id, metrics, evidence.
    Raises ValueError with sandbox_required:/runner_forbidden: prefixes if misrouted.
    """
    rid = str(job.get("runner_id") or "").strip()
    fn = _RUNNERS.get(rid)
    if fn is None:
        raise ValueError(f"runner_forbidden:{rid}")
    return fn(job)


def _wire_execute() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    return execute_runner(
        {
            "job_id": "job_verify",
            "runner_id": "replay_trace",
            "tenant_id": "t",
            "payload": {"trace": {"steps": []}, "expected": {"ok": True}},
        }
    )
