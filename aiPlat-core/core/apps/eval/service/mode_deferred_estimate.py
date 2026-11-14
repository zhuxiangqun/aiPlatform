"""M2 deferred-mode estimate — multi_agent / pipeline / operator.

Honesty:
- deferred ≠ unknown (disclose + block covered claims; unknown not in denominator)
- no live exam / no rank_eligible until runtime_parts wired
- estimate charter only; does not create_agent workers as one primary column
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml

from core.apps.eval.service.agent_impl_mode import (
    DEFERRED_MODES,
    AgentImplModeError,
    load_mode_core_matrix,
    resolve_impl_modes,
)
from core.apps.eval.service.capability_case_bank import default_seed_dir

ESTIMATE_SCHEMA = "eval.m2_deferred_estimate.v1"
ESTIMATE_FILENAME = "m2_deferred_estimate.v1.yaml"
RUNTIME_PARTS_SCHEMA = "eval.runtime_parts.m2.v1"


class ModeDeferredEstimateError(ValueError):
    """Fail-closed M2 estimate error."""


def default_m2_estimate_path() -> Path:
    """default_m2_estimate_path。
    """
    return default_seed_dir() / ESTIMATE_FILENAME


def load_m2_deferred_estimate(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """加载 m2_deferred_estimate。

    Args:
        path: 文件或目录路径。
    """
    p = Path(path) if path else default_m2_estimate_path()
    if not p.is_file():
        raise ModeDeferredEstimateError(f"m2_estimate_missing:{p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ModeDeferredEstimateError("m2_estimate_not_object")
    if str(raw.get("schema") or "") != ESTIMATE_SCHEMA:
        raise ModeDeferredEstimateError(f"m2_estimate_schema:{raw.get('schema')}")
    return dict(raw)


def validate_runtime_parts(
    parts: Sequence[Mapping[str, Any]] | None,
    *,
    mode: str,
    estimate: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Validate runtime_parts shape for a deferred mode (fail closed).

    Args:
        parts: parts 参数。
        mode: 执行/评测模式。
        estimate: estimate 参数。
    """
    est = dict(estimate) if estimate is not None else load_m2_deferred_estimate()
    mode_key = str(mode or "").strip().lower()
    modes = est.get("deferred_modes") if isinstance(est.get("deferred_modes"), Mapping) else {}
    cfg = modes.get(mode_key) if isinstance(modes.get(mode_key), Mapping) else None
    if cfg is None:
        return {
            "ok": False,
            "errors": [f"m2_mode_not_in_estimate:{mode_key}"],
            "mode": mode_key,
        }
    required = list(cfg.get("runtime_parts_required") or [])
    got = [dict(p) for p in (parts or []) if isinstance(p, Mapping)]
    errors: List[str] = []
    if not got:
        errors.append("runtime_parts_empty")
    by_id = {str(p.get("part_id") or p.get("sub_id") or "").strip(): p for p in got}
    for req in required:
        if not isinstance(req, Mapping):
            continue
        pid = str(req.get("part_id") or "").strip()
        must = [str(x) for x in (req.get("must_fields") or []) if str(x).strip()]
        # At least one part matching part_id or role/stage naming
        match = by_id.get(pid)
        if match is None:
            # allow role/stage_id equals part_id
            for p in got:
                if str(p.get("role") or "") == pid or str(p.get("stage_id") or "") == pid:
                    match = p
                    break
        if match is None:
            errors.append(f"missing_part:{pid}")
            continue
        for f in must:
            if f == "sub_id" and (match.get("sub_id") or match.get("part_id")):
                continue
            if not match.get(f):
                errors.append(f"missing_field:{pid}.{f}")
        allowed_tiers = {
            str(x) for x in (req.get("runtime_tier_allowed") or []) if str(x).strip()
        }
        tier = str(match.get("runtime_tier") or "").strip()
        if allowed_tiers and tier and tier not in allowed_tiers:
            errors.append(f"tier_not_allowed:{pid}:{tier}")
    return {
        "ok": not errors,
        "errors": errors,
        "mode": mode_key,
        "n_parts": len(got),
        "schema": RUNTIME_PARTS_SCHEMA,
    }


def estimate_m2_deferred_modes(
    *,
    seed_dir: Optional[Path] = None,
    impl_source: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Produce M2 estimate report: blockers, days, runtime_parts deps; no live.

    Args:
        seed_dir: 种子目录；None 用默认。
        impl_source: impl_source 参数。
    """
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    estimate = load_m2_deferred_estimate(path=root / ESTIMATE_FILENAME)
    try:
        matrix = load_mode_core_matrix(path=root / "mode_core_capabilities.v1.yaml")
    except AgentImplModeError as exc:
        matrix = {"error": str(exc)}

    matrix_deferred = {
        str(x).strip()
        for x in (matrix.get("deferred_modes") or [])
        if str(x).strip()
    } if isinstance(matrix, Mapping) else set()
    est_modes = estimate.get("deferred_modes") if isinstance(estimate.get("deferred_modes"), Mapping) else {}
    mode_rows: Dict[str, Any] = {}
    total_days = 0
    for mid, cfg in est_modes.items():
        if not isinstance(cfg, Mapping):
            continue
        days = int(((cfg.get("estimate") or {}) if isinstance(cfg.get("estimate"), Mapping) else {}).get("engineering_days") or 0)
        total_days += days
        mode_rows[mid] = {
            "status": cfg.get("status") or "deferred",
            "m_phase": cfg.get("m_phase") or "m2",
            "blockers": list(cfg.get("blockers") or []),
            "runtime_parts_required": list(cfg.get("runtime_parts_required") or []),
            "estimate": cfg.get("estimate"),
            "live_exam_allowed": False,
            "rank_eligible_allowed": False,
            "neq_unknown": True,
        }

    resolved = resolve_impl_modes(impl_source or {"agent_type": "multi_agent"})
    gate = estimate.get("gate") if isinstance(estimate.get("gate"), Mapping) else {}

    aligned = matrix_deferred == set(est_modes.keys()) or matrix_deferred >= set(est_modes.keys())
    return {
        "schema": ESTIMATE_SCHEMA,
        "phase": "m2",
        "ok": bool(mode_rows) and aligned,
        "deferred_modes": mode_rows,
        "total_engineering_days_est": total_days,
        "matrix_deferred_modes": sorted(matrix_deferred),
        "matrix_aligned": aligned,
        "resolve_sample": {
            "primary": resolved.get("primary"),
            "deferred_as": resolved.get("deferred_as"),
            "neq_unknown": resolved.get("primary") == "deferred",
        },
        "runtime_parts_contract": estimate.get("runtime_parts_contract"),
        "gate": {
            "live_exam_allowed": bool(gate.get("live_exam_allowed")),
            "rank_eligible_allowed": bool(gate.get("rank_eligible_allowed")),
            "reason": str(gate.get("reason") or "m2_estimate_only"),
        },
        "claim_eligible": False,
        "rank_claim": False,
        "accuracy_claim": False,
        "honesty": (
            "M2 estimate only; deferred≠unknown; no live create_agent column; "
            "runtime_parts must be wired before Track A covered / Track B rank"
        ),
    }


def assert_m2_not_live(mode: str) -> None:
    """Fail closed if caller tries to open deferred mode as live exam.

    Args:
        mode: 执行/评测模式。
    """
    m = str(mode or "").strip().lower()
    if m in DEFERRED_MODES or m == "deferred":
        raise ModeDeferredEstimateError(f"m2_live_forbidden:{m}")
