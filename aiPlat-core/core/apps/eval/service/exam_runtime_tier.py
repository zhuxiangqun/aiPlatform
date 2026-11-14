"""Exam runtime_tier / target_runtime / runtime_claim (eval-exam-runtime-tiers.md v1.4).

Honesty only — does not change model selection or execute path.
runtime_tier = actual execution plane; target_runtime = intended delivery form.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Literal, Optional, Sequence

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
    """Agent exam 运行时标注：dry-run → fixture；live → workspace_execute。

    Args:
        live: 是否走真实 Execute（非 fixture）。

    Returns:
        含 ``runtime_tier`` / ``target_runtime`` / ``runtime_claim`` 等字段的 dict。
    """
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
    """外部 HTTP 拉测运行时标注：dry → fixture；live pull → external_pull。

    Args:
        live: 是否发起计分拉取。

    Returns:
        运行时标注 dict。
    """
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
    """Skill suite（platform skill_evals）运行时标注。

    与验管道 skill_suite Job、Agent exam 不同路径。
    trigger：仅路由候选 → fixture；quality：经 skill_manager 调用 → core_skill_execute。

    Args:
        eval_kind: ``trigger`` 或 ``quality``。
        mode: 触发评测模式标签（写入 ``execution_mode``）。

    Returns:
        运行时标注 dict。
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


def annotate_prompt_plan_runtime(*, live: bool) -> Dict[str, Any]:
    """Prompt Plan 链 exam 运行时（≠ 页面/DB prompt_eval）。

    Args:
        live: 是否 live Plan 路径。

    Returns:
        委托 ``annotate_typed_plan_runtime`` 的标注 dict。
    """
    from core.apps.eval.service.typed_plan_exam import annotate_typed_plan_runtime

    return annotate_typed_plan_runtime(object_type="prompt", live=live)


def annotate_workflow_plan_runtime(*, live: bool) -> Dict[str, Any]:
    """Workflow Plan 链 exam 运行时（fixture + target workspace_execute）。

    Args:
        live: 是否 live Plan 路径。

    Returns:
        运行时标注 dict。
    """
    from core.apps.eval.service.typed_plan_exam import annotate_typed_plan_runtime

    return annotate_typed_plan_runtime(object_type="workflow", live=live)


def annotate_model_plan_runtime(*, live: bool) -> Dict[str, Any]:
    """Model Plan 链 exam 运行时（≠ model leaderboard）。

    Args:
        live: 是否 live Plan 路径。

    Returns:
        运行时标注 dict。
    """
    from core.apps.eval.service.typed_plan_exam import annotate_typed_plan_runtime

    return annotate_typed_plan_runtime(object_type="model", live=live)


def annotate_dataset_plan_runtime(*, live: bool = False) -> Dict[str, Any]:
    """Dataset Plan 链 exam 运行时（fixture_table；≠ KB sample）。

    Args:
        live: 是否 live；默认 False。

    Returns:
        运行时标注 dict。
    """
    from core.apps.eval.service.typed_plan_exam import annotate_typed_plan_runtime

    return annotate_typed_plan_runtime(object_type="dataset", live=live)


def annotate_generated_app_runtime(
    *,
    mode: Literal["runs_eval", "pi_offline", "pi_live"],
) -> Dict[str, Any]:
    """生成应用评测运行时：``target_runtime`` 恒为 pi；仅 Pi 宿主真正跑过时 ``runtime_tier=pi``。

    Args:
        mode: ``runs_eval``（平台路径未接 Pi）/ ``pi_offline``（结构导出）/
            ``pi_live``（Pi CLI 已执行）。

    Returns:
        运行时标注 dict。
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
    """把运行时标注合并进响应；永不把 ``accuracy_claim`` 升为 true。

    若 ``ann``/``out`` 含 ``runtime_parts``，顶层 tier/claim 由
    ``summarize_runtime_parts`` 重写（异构 → mixed，claim=false）。

    Args:
        out: 待合并的响应 dict（原地修改）。
        ann: 标注字段 dict。

    Returns:
        合并后的 ``out``。
    """
    if not isinstance(out, dict):
        return out
    for k in _RUNTIME_KEYS:
        if k in ann:
            out[k] = ann[k]
    parts = ann.get("runtime_parts") if isinstance(ann, dict) else None
    if parts is None:
        parts = out.get("runtime_parts")
    if isinstance(parts, (list, tuple)) and parts:
        summary = summarize_runtime_parts(parts)
        out["runtime_parts"] = summary.get("runtime_parts") or parts
        if summary.get("runtime_tier") is not None:
            out["runtime_tier"] = summary["runtime_tier"]
        out["runtime_claim"] = bool(summary.get("runtime_claim"))
        out["runtime_claim_reason"] = str(
            summary.get("runtime_claim_reason") or out.get("runtime_claim_reason") or ""
        )
    out["accuracy_claim"] = False
    return out


def summarize_runtime_parts(
    parts: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """汇总 ``runtime_parts``（系统/多入口报告，Runtime Tiers §7.1）。

    同质 tier → 该 tier；异构 → ``runtime_tier=mixed`` 且 ``runtime_claim=false``。
    禁止把异构宿主塌缩成单一代表 tier。

    Args:
        parts: 子入口标注序列；每项至少含 ``sub_id`` / ``runtime_tier``。

    Returns:
        含 ``runtime_parts`` / ``runtime_tier`` / ``runtime_claim`` / ``mixed`` 的汇总 dict。
    """
    cleaned: List[Dict[str, Any]] = []
    for raw in parts or []:
        if not isinstance(raw, Mapping):
            continue
        sub = str(raw.get("sub_id") or "").strip()
        tier = str(raw.get("runtime_tier") or "").strip()
        if not sub or not tier:
            continue
        row: Dict[str, Any] = {"sub_id": sub, "runtime_tier": tier}
        for k in ("target_runtime", "runner_id", "execution_mode", "result"):
            if raw.get(k) is not None:
                row[k] = raw.get(k)
        if "runtime_claim" in raw:
            row["runtime_claim"] = bool(raw.get("runtime_claim"))
        cleaned.append(row)
    if not cleaned:
        return {
            "runtime_parts": [],
            "runtime_claim": False,
            "runtime_claim_reason": "no runtime_parts",
            "mixed": False,
        }
    tiers = sorted({str(p["runtime_tier"]) for p in cleaned})
    if len(tiers) == 1:
        all_claim = all(p.get("runtime_claim") is True for p in cleaned)
        return {
            "runtime_parts": cleaned,
            "runtime_tier": tiers[0],
            "runtime_claim": all_claim,
            "runtime_claim_reason": (
                f"homogeneous runtime_parts tier={tiers[0]}"
                if all_claim
                else f"homogeneous tier={tiers[0]} but not all parts claimable"
            ),
            "mixed": False,
        }
    return {
        "runtime_parts": cleaned,
        "runtime_tier": "mixed",
        "runtime_claim": False,
        "runtime_claim_reason": (
            f"heterogeneous runtime_parts tiers=[{','.join(tiers)}] — see parts; do not collapse"
        ),
        "mixed": True,
    }
