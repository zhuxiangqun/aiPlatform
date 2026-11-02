"""B2 runner allowlist — fail-closed classification (EVAL_RUNTIME_CONTRACT §3).

Honesty: process_split_authorized stays false; tool/sandbox runners wait for B3.
"""
from __future__ import annotations

from typing import Literal

# B2 may enqueue + Worker-execute (no tool/sandbox).
B2_ALLOWED: frozenset[str] = frozenset(
    {
        "replay_trace",
        "prompt_eval",
        "kb_rag",
        "code_review_gold",
        "arena",  # pure-text only; tool use → sandbox_required at Worker
    }
)

# Need B3 sandbox — never silently run on B2.
B2_SANDBOX_REQUIRED: frozenset[str] = frozenset(
    {
        "skill_suite",
        "http_probe",
        "cli_probe",
        "security_redteam",
    }
)

RunnerClass = Literal["allowed", "sandbox_required", "forbidden"]


def classify_runner(runner_id: str) -> RunnerClass:
    rid = (runner_id or "").strip()
    if not rid:
        return "forbidden"
    if rid in B2_ALLOWED:
        return "allowed"
    if rid in B2_SANDBOX_REQUIRED:
        return "sandbox_required"
    return "forbidden"


def is_enqueue_allowed(runner_id: str) -> bool:
    return classify_runner(runner_id) == "allowed"


def assert_runner_allowed_for_execute(runner_id: str) -> None:
    """Worker dual-point: raise ValueError with stable code prefix if not allowed."""
    kind = classify_runner(runner_id)
    if kind == "allowed":
        return
    if kind == "sandbox_required":
        raise ValueError(f"sandbox_required:{runner_id}")
    raise ValueError(f"runner_forbidden:{runner_id}")


# method_verify warm calls
_ = classify_runner("prompt_eval")
_ = is_enqueue_allowed("skill_suite")
