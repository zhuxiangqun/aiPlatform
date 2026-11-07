"""Exam runtime_tier / target_runtime / runtime_claim (eval-exam-runtime-tiers.md v1.3).

Honesty only — does not change model selection or execute path.
runtime_tier = actual execution plane; target_runtime = intended delivery form.
"""
from __future__ import annotations

from typing import Any, Dict, Literal

RuntimeTier = Literal[
    "fixture",
    "pi",
    "workspace_execute",
    "core_skill_execute",
    "eval_worker",
    "external_pull",
]

VALID_TIERS = frozenset(
    {
        "fixture",
        "pi",
        "workspace_execute",
        "core_skill_execute",
        "eval_worker",
        "external_pull",
    }
)

_RUNTIME_KEYS = (
    "runtime_tier",
    "target_runtime",
    "runtime_claim",
    "runtime_claim_reason",
    "execution_mode",
)


def annotate_agent_exam_runtime(*, live: bool) -> Dict[str, Any]:
    """Agent exam panel: dry-run → fixture; live → workspace_execute."""
    if live:
        return {
            "runtime_tier": "workspace_execute",
            "target_runtime": "workspace_execute",
            "runtime_claim": True,
            "runtime_claim_reason": (
                "结论仅适用于本命名工作区 Execute 路径（真实 AgentInfo）；"
                "≠ eval_worker；≠ 执行平面已迁移；accuracy_claim=false"
            ),
            "accuracy_claim": False,
        }
    return {
        "runtime_tier": "fixture",
        "target_runtime": "workspace_execute",
        "runtime_claim": False,
        "runtime_claim_reason": "fixture does not execute subject",
        "accuracy_claim": False,
    }


def annotate_external_exam_runtime(*, live: bool) -> Dict[str, Any]:
    """External HTTP pull: dry (no scored pull) → fixture; live pull → external_pull."""
    if live:
        return {
            "runtime_tier": "external_pull",
            "target_runtime": "external_pull",
            "runtime_claim": True,
            "runtime_claim_reason": (
                "结论仅适用于该外部 HTTP 拉模式目标；≠ workspace_execute；≠ pi；"
                "accuracy_claim=false"
            ),
            "accuracy_claim": False,
        }
    return {
        "runtime_tier": "fixture",
        "target_runtime": "external_pull",
        "runtime_claim": False,
        "runtime_claim_reason": (
            "external_pull dry-run validates target/paper only; no scored pull yet"
        ),
        "accuracy_claim": False,
    }


def annotate_skill_eval_runtime(
    *,
    eval_kind: str = "trigger",
    mode: str = "heuristic",
) -> Dict[str, Any]:
    """Skill suite (platform skill_evals) — ≠ 验管道 skill_suite Job；≠ Agent exam.

    trigger: routing candidates only → fixture (subject handler not executed).
    quality: Core skill_manager invokes target skill → core_skill_execute.
    """
    kind = str(eval_kind or "trigger").strip().lower()
    md = str(mode or "heuristic").strip().lower()
    if kind == "quality":
        return {
            "runtime_tier": "core_skill_execute",
            "target_runtime": "core_skill_execute",
            "runtime_claim": True,
            "runtime_claim_reason": (
                "结论仅适用于经 Core skill_manager 调用该 Skill 的路径；"
                "≠ workspace_execute agent；≠ eval_worker；accuracy_claim=false"
            ),
            "accuracy_claim": False,
            "execution_mode": "skill_manager_quality",
        }
    return {
        "runtime_tier": "fixture",
        "target_runtime": "core_skill_execute",
        "runtime_claim": False,
        "runtime_claim_reason": (
            f"skill trigger {md}: routing candidates only; "
            "target skill handler not executed"
        ),
        "accuracy_claim": False,
        "execution_mode": f"skill_trigger_{md}",
    }


def annotate_generated_app_runtime(
    *,
    mode: Literal["runs_eval", "pi_offline", "pi_live"],
) -> Dict[str, Any]:
    """Generated-app eval — target_runtime always pi; runtime_tier only when Pi host ran.

    modes:
      runs_eval   — platform runs_eval path; Pi host not used → fixture + target=pi
      pi_offline  — export/structural only; pi CLI not invoked → fixture + target=pi
      pi_live     — pi CLI (or equivalent) executed against the bundle → pi
    """
    if mode == "pi_live":
        return {
            "runtime_tier": "pi",
            "target_runtime": "pi",
            "runtime_claim": True,
            "runtime_claim_reason": (
                "结论仅适用于厂外 Pi 薄宿主交付态冒烟；≠ workspace_execute；"
                "≠ PolicyGate；accuracy_claim=false"
            ),
            "accuracy_claim": False,
        }
    if mode == "pi_offline":
        return {
            "runtime_tier": "fixture",
            "target_runtime": "pi",
            "runtime_claim": False,
            "runtime_claim_reason": (
                "target_runtime=pi but pi CLI not invoked; structural/export only"
            ),
            "accuracy_claim": False,
        }
    return {
        "runtime_tier": "fixture",
        "target_runtime": "pi",
        "runtime_claim": False,
        "runtime_claim_reason": (
            "target_runtime=pi; platform runs_eval only — pi host not wired for this result"
        ),
        "accuracy_claim": False,
    }


def merge_runtime_fields(out: Dict[str, Any], ann: Dict[str, Any]) -> Dict[str, Any]:
    """Merge annotation into response; never upgrade accuracy_claim to true."""
    if not isinstance(out, dict):
        return out
    for k in _RUNTIME_KEYS:
        if k in ann:
            out[k] = ann[k]
    out["accuracy_claim"] = False
    return out
