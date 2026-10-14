"""应用工厂「跑通」晋升门（2026-09）。

四维跑通 + multi_agent 五条 AND 的机器可读契约。
与 generated_conformance.validate_manifest 配合：本模块管阈值/清单；
manifest 字段硬校验在 conformance。

2026-10 可解释增强：每条检查附 how_to_fix / missing；汇总 next_actions + summary，
供 API / 部署 rejected_artifacts.fix_hint / 工厂 UI 展示「缺哪条、还差什么」。
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

# Fallback copy when YAML omits how_to_fix (keep YAML SoT; these are safety nets).
_DEFAULT_HOW_TO_FIX: Dict[str, str] = {
    "orthogonal_subtasks": (
        "在 upgrade_criteria.orthogonal_subtasks 列出 ≥3 个可并行/可隔离的子任务名"
        "（不是同一流水线的串行步骤）"
    ),
    "single_agent_gap": (
        "先以 mode=single 跑满 N≥20 次有效 hop；成功率须低于起步阈值（默认 0.80），"
        "且失败含 planning 或 tool_selection；再填 single_agent_gap"
    ),
    "routing_benefit": (
        "用 ≥8 字说明拆分后的路由收益（不同 skill 集或上下文溢出），"
        "写入 upgrade_criteria.routing_benefit"
    ),
    "policy_gate_stable": (
        "确认工具副作用均经 PolicyGate，且已稳定 ≥1 迭代后，"
        "将 upgrade_criteria.policy_gate_stable 设为 true"
    ),
    "contracted_handoff": (
        "跨 Agent 交接须走阶段契约 + schema 门（禁止自由文本互调）；"
        "就绪后将 upgrade_criteria.contracted_handoff 设为 true"
    ),
}


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


def _and_meta(cfg: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """id → {description, how_to_fix} from YAML (+ defaults)."""
    out: Dict[str, Dict[str, str]] = {}
    for item in cfg.get("multi_agent_upgrade_and") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        rid = str(item["id"])
        out[rid] = {
            "description": str(item.get("description") or rid),
            "how_to_fix": str(
                item.get("how_to_fix") or _DEFAULT_HOW_TO_FIX.get(rid, f"补齐 {rid}")
            ),
        }
    for rid, fix in _DEFAULT_HOW_TO_FIX.items():
        out.setdefault(rid, {"description": rid, "how_to_fix": fix})
    return out


def format_upgrade_fix_hint(result: Dict[str, Any], *, max_actions: int = 3) -> str:
    """Compact Chinese hint for deploy rejected_artifacts / UI toasts."""
    if result.get("ok"):
        return "五条 AND 已满足；可保持 mode=multi_agent"
    actions = [str(a) for a in (result.get("next_actions") or []) if a][:max_actions]
    summary = str(result.get("summary") or "").strip()
    if actions:
        body = "；".join(actions)
        return f"{summary} → {body}" if summary else body
    blockers = [str(b) for b in (result.get("blockers") or []) if b][:max_actions]
    if blockers:
        return "；".join(blockers)
    return "默认 mode=single；升 multi_agent 需 rationale+success_metrics+upgrade_criteria 五条 AND"


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
    """评估四维「跑通」。返回 {ok, checks[], blockers[], next_actions[], summary}。"""
    cfg = (config or load_promotion_gate()).get("run_through") or {}
    min_runs = int(cfg.get("min_runs", 20))
    target = float(
        cfg.get("success_rate_mature" if mature else "success_rate_start", 0.80)
    )
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []
    next_actions: List[str] = []

    def _add(name: str, ok: bool, detail: str, how_to_fix: str = "") -> None:
        checks.append(
            {
                "name": name,
                "ok": ok,
                "detail": detail,
                "how_to_fix": how_to_fix,
                "missing": "" if ok else detail,
            }
        )
        if not ok:
            blockers.append(f"{name}: {detail}")
            if how_to_fix:
                next_actions.append(how_to_fix)

    rate_ok = n_runs >= min_runs and success_rate >= target and failures_missing_stage == 0
    _add(
        "e2e_success_rate",
        rate_ok,
        f"n_runs={n_runs} (need ≥{min_runs}), rate={success_rate:.3f} (need ≥{target}), "
        f"failures_missing_stage={failures_missing_stage}",
        how_to_fix=(
            f"继续有效 hop 至 N≥{min_runs}，成功率≥{target}，且每次失败带 failed_stage"
            if not rate_ok
            else ""
        ),
    )
    _add(
        "failed_stage_attribution",
        failures_missing_stage == 0,
        "每次失败必须带可枚举 failed_stage，否则该次不计入有效统计",
        how_to_fix=(
            "为失败 hop 补全 failed_stage（planning/tool_selection/tool_execution/"
            "response_synthesis/verification）"
            if failures_missing_stage
            else ""
        ),
    )
    conf_ok = bool(conformance_green and real_tests_green and physical_evidence)
    _add(
        "conformance_real_tests",
        conf_ok,
        f"conformance={conformance_green}, real_tests={real_tests_green}, "
        f"physical_evidence={physical_evidence}",
        how_to_fix=(
            "跑通真实测试并保留非 mock 物理产物；部署时 conformance 拒绝数须为 0"
            if not conf_ok
            else ""
        ),
    )
    _add(
        "policy_gate",
        bool(policy_gate_closed),
        "所有工具调用须在副作用前经 PolicyGate（ALLOW/APPROVAL_REQUIRED/DENY）",
        how_to_fix=(
            "确认工具路径经 PolicyGate，禁止绕过 sys_tool_call 的副作用"
            if not policy_gate_closed
            else ""
        ),
    )
    passed = sum(1 for c in checks if c.get("ok"))
    summary = (
        f"四维跑通通过 {passed}/{len(checks)}"
        if blockers
        else "四维跑通全部满足"
    )
    return {
        "ok": len(blockers) == 0,
        "checks": checks,
        "blockers": blockers,
        "next_actions": next_actions,
        "summary": summary,
        "external_message": (config or load_promotion_gate()).get("external_message", ""),
    }


def evaluate_multi_agent_upgrade(
    criteria: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """五条 AND。criteria 来自 manifest.upgrade_criteria。

    返回除 ok/checks/blockers 外还含：
    - missing_criteria: 未通过的 id 列表
    - next_actions: 人话下一步（按检查顺序）
    - summary: 「通过 x/5；缺：…」
    """
    cfg = config or load_promotion_gate()
    meta = _and_meta(cfg)
    required = [x["id"] for x in (cfg.get("multi_agent_upgrade_and") or []) if x.get("id")]
    c = criteria if isinstance(criteria, dict) else {}
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []
    missing_criteria: List[str] = []
    next_actions: List[str] = []

    def _fail(name: str, detail: str, missing: str) -> None:
        m = meta.get(name) or {}
        how = str(m.get("how_to_fix") or _DEFAULT_HOW_TO_FIX.get(name, f"补齐 {name}"))
        checks.append(
            {
                "name": name,
                "ok": False,
                "detail": detail,
                "description": str(m.get("description") or name),
                "how_to_fix": how,
                "missing": missing,
            }
        )
        blockers.append(f"{name}: {missing}")
        missing_criteria.append(name)
        next_actions.append(how)

    def _pass(name: str, detail: str) -> None:
        m = meta.get(name) or {}
        checks.append(
            {
                "name": name,
                "ok": True,
                "detail": detail,
                "description": str(m.get("description") or name),
                "how_to_fix": "",
                "missing": "",
            }
        )

    # 1 orthogonal_subtasks
    subs = c.get("orthogonal_subtasks")
    n_subs = len(subs) if isinstance(subs, list) else 0
    if isinstance(subs, list) and n_subs >= 3:
        _pass("orthogonal_subtasks", f"count={n_subs}")
    else:
        _fail(
            "orthogonal_subtasks",
            f"count={n_subs}",
            f"需要 ≥3 个正交子任务声明，当前 {n_subs}",
        )

    # 2 single_agent_gap
    gap = c.get("single_agent_gap") if isinstance(c.get("single_agent_gap"), dict) else {}
    n_runs = int(gap.get("n_runs") or 0)
    rate = float(gap.get("success_rate") if gap.get("success_rate") is not None else 1.0)
    stages = gap.get("failed_stages") or []
    start = float((cfg.get("run_through") or {}).get("success_rate_start", 0.80))
    ok_stages = isinstance(stages, list) and any(
        s in ("planning", "tool_selection") for s in stages
    )
    parts: List[str] = []
    if n_runs < 20:
        parts.append(f"有效跑次不足（n_runs={n_runs}，需 ≥20）")
    if rate >= start:
        parts.append(f"成功率未低于起步阈值（rate={rate}，需 <{start}）")
    if not ok_stages:
        parts.append(
            f"失败阶段未含 planning/tool_selection（failed_stages={stages!r}）"
        )
    if not parts:
        _pass(
            "single_agent_gap",
            f"n_runs={n_runs}, rate={rate}, failed_stages={stages}",
        )
    else:
        _fail(
            "single_agent_gap",
            f"n_runs={n_runs}, rate={rate}, failed_stages={stages}",
            "；".join(parts),
        )

    # 3 routing_benefit
    rb = c.get("routing_benefit")
    rb_ok = isinstance(rb, str) and len(rb.strip()) >= 8
    if rb_ok:
        _pass("routing_benefit", str(rb)[:80])
    else:
        _fail(
            "routing_benefit",
            str(rb)[:80] if rb is not None else "",
            "需非空说明（≥8 字）说明拆分的路由收益",
        )

    # 4 policy_gate_stable
    if c.get("policy_gate_stable") is True:
        _pass("policy_gate_stable", "true")
    else:
        _fail(
            "policy_gate_stable",
            str(c.get("policy_gate_stable")),
            "必须为 true（PolicyGate 已稳定、可分 Agent 授权）",
        )

    # 5 contracted_handoff
    if c.get("contracted_handoff") is True:
        _pass("contracted_handoff", "true")
    else:
        _fail(
            "contracted_handoff",
            str(c.get("contracted_handoff")),
            "必须为 true（阶段契约 + schema 门，禁止自由文本互调）",
        )

    # ensure we tracked all configured ids
    for rid in required:
        if not any(ch["name"] == rid for ch in checks):
            _fail(rid, "not_checked", f"{rid}: 未实现检查")

    total = len(checks) or 5
    passed = sum(1 for ch in checks if ch.get("ok"))
    if missing_criteria:
        summary = (
            f"五条 AND 通过 {passed}/{total}；缺："
            + "、".join(missing_criteria)
        )
    else:
        summary = f"五条 AND 全部满足（{passed}/{total}）"

    return {
        "ok": len(blockers) == 0,
        "checks": checks,
        "blockers": blockers,
        "missing_criteria": missing_criteria,
        "next_actions": next_actions,
        "summary": summary,
    }
