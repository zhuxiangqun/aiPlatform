"""应用工厂「跑通」晋升门（2026-09）。

四维跑通 + multi_agent 五条 AND 的机器可读契约。
与 generated_conformance.validate_manifest 配合：本模块管阈值/清单；
manifest 字段硬校验在 conformance。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "promotion_gate.yaml"
_cache: Optional[Dict[str, Any]] = None

RUNTIME_FAILED_STAGES = (
    "planning",
    "tool_selection",
    "tool_execution",
    "response_synthesis",
    "verification",
)


def load_promotion_gate(path: Optional[str] = None) -> Dict[str, Any]:
    global _cache
    p = Path(path) if path else _DEFAULT_PATH
    if _cache is None or str(p) != str(_DEFAULT_PATH):
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"promotion_gate not a mapping: {p}")
        if path is None:
            _cache = data
        return data
    return _cache


def evaluate_run_through(
    *,
    n_runs: int,
    success_rate: float,
    failures_missing_stage: int = 0,
    conformance_green: bool = False,
    real_tests_green: bool = False,
    physical_evidence: bool = False,
    policy_gate_closed: bool = False,
    mature: bool = False,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """评估四维「跑通」。返回 {ok, checks[], blockers[]}。"""
    cfg = (config or load_promotion_gate()).get("run_through") or {}
    min_runs = int(cfg.get("min_runs", 20))
    target = float(
        cfg.get("success_rate_mature" if mature else "success_rate_start", 0.80)
    )
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []

    def _add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            blockers.append(f"{name}: {detail}")

    _add(
        "e2e_success_rate",
        n_runs >= min_runs and success_rate >= target and failures_missing_stage == 0,
        f"n_runs={n_runs} (need ≥{min_runs}), rate={success_rate:.3f} (need ≥{target}), "
        f"failures_missing_stage={failures_missing_stage}",
    )
    _add(
        "failed_stage_attribution",
        failures_missing_stage == 0,
        "每次失败必须带可枚举 failed_stage，否则该次不计入有效统计",
    )
    _add(
        "conformance_real_tests",
        bool(conformance_green and real_tests_green and physical_evidence),
        f"conformance={conformance_green}, real_tests={real_tests_green}, "
        f"physical_evidence={physical_evidence}",
    )
    _add(
        "policy_gate",
        bool(policy_gate_closed),
        "所有工具调用须在副作用前经 PolicyGate（ALLOW/APPROVAL_REQUIRED/DENY）",
    )
    return {
        "ok": len(blockers) == 0,
        "checks": checks,
        "blockers": blockers,
        "external_message": (config or load_promotion_gate()).get("external_message", ""),
    }


def evaluate_multi_agent_upgrade(
    criteria: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """五条 AND。criteria 来自 manifest.upgrade_criteria。"""
    cfg = config or load_promotion_gate()
    required = [x["id"] for x in (cfg.get("multi_agent_upgrade_and") or []) if x.get("id")]
    c = criteria if isinstance(criteria, dict) else {}
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []

    # 1 orthogonal_subtasks
    subs = c.get("orthogonal_subtasks")
    ok1 = isinstance(subs, list) and len(subs) >= 3
    checks.append({"name": "orthogonal_subtasks", "ok": ok1, "detail": f"count={len(subs) if isinstance(subs, list) else 0}"})
    if not ok1:
        blockers.append("orthogonal_subtasks: 需要 ≥3 个正交子任务声明")

    # 2 single_agent_gap
    gap = c.get("single_agent_gap") if isinstance(c.get("single_agent_gap"), dict) else {}
    n_runs = int(gap.get("n_runs") or 0)
    rate = float(gap.get("success_rate") if gap.get("success_rate") is not None else 1.0)
    stages = gap.get("failed_stages") or []
    start = float((cfg.get("run_through") or {}).get("success_rate_start", 0.80))
    ok_stages = isinstance(stages, list) and any(
        s in ("planning", "tool_selection") for s in stages
    )
    ok2 = n_runs >= 20 and rate < start and ok_stages
    checks.append({
        "name": "single_agent_gap",
        "ok": ok2,
        "detail": f"n_runs={n_runs}, rate={rate}, failed_stages={stages}",
    })
    if not ok2:
        blockers.append(
            "single_agent_gap: 需 N≥20 且成功率低于起步阈值，且失败含 planning/tool_selection"
        )

    # 3 routing_benefit
    rb = c.get("routing_benefit")
    ok3 = isinstance(rb, str) and len(rb.strip()) >= 8
    checks.append({"name": "routing_benefit", "ok": ok3, "detail": str(rb)[:80]})
    if not ok3:
        blockers.append("routing_benefit: 需非空说明（≥8 字）")

    # 4 policy_gate_stable
    ok4 = c.get("policy_gate_stable") is True
    checks.append({"name": "policy_gate_stable", "ok": ok4, "detail": str(c.get("policy_gate_stable"))})
    if not ok4:
        blockers.append("policy_gate_stable: 必须为 true")

    # 5 contracted_handoff
    ok5 = c.get("contracted_handoff") is True
    checks.append({"name": "contracted_handoff", "ok": ok5, "detail": str(c.get("contracted_handoff"))})
    if not ok5:
        blockers.append("contracted_handoff: 必须为 true（阶段契约+schema 门）")

    # ensure we tracked all configured ids
    for rid in required:
        if not any(ch["name"] == rid for ch in checks):
            blockers.append(f"{rid}: 未实现检查")

    return {"ok": len(blockers) == 0, "checks": checks, "blockers": blockers}
