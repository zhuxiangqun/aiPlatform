"""演化评估预算硬上限（实施计划 §10.3）。

默认未批准（approved=false）；须人工 approve_budget 后才算 G0 预算条件满足。
超限自动拒绝，不无限搜索。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

_POLICY: Optional[Dict[str, Any]] = None


def _policy_path() -> Path:
    """预算策略落盘路径。"""
    import tempfile

    root = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    p = Path(root) / "evo_compute" / "budget"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p / "policy.json"
    except OSError:
        p = Path(tempfile.gettempdir()) / "aiplat_evo_compute" / "budget"
        p.mkdir(parents=True, exist_ok=True)
        return p / "policy.json"


def default_budget_policy() -> Dict[str, Any]:
    """默认试点评估预算（硬上限；未批准）。

    Returns:
        预算字典；``approved`` 恒为 False 直至人工签字。
    """
    return {
        "policy_id": "evo_budget_g0_v1",
        "max_candidates": 50,
        "max_generations": 10,
        "max_llm_calls": 200,
        "max_tokens": 500_000,
        "max_wall_time_sec": 3600,
        "max_cost_usd": 25.0,
        "approved": False,
        "approver": "",
        "approved_at": None,
        "evidence_ref": "",
    }


def get_budget_policy() -> Dict[str, Any]:
    """读取当前预算策略（内存 → 磁盘 → 默认）。

    Returns:
        含 policy 与 ok 的回执。
    """
    global _POLICY
    if _POLICY is not None:
        return {
            "ok": True,
            "policy": dict(_POLICY),
            "approved": bool(_POLICY.get("approved")),
            "g0_foundation": True,
            "certified": False,
        }
    path = _policy_path()
    data = None
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # 损坏落盘回退默认策略；不抬高 approved
            data = None
            _ = exc
    if isinstance(data, dict):
        _POLICY = data
        return {
            "ok": True,
            "policy": dict(data),
            "approved": bool(data.get("approved")),
            "g0_foundation": True,
            "certified": False,
        }
    pol = default_budget_policy()
    return {
        "ok": True,
        "policy": pol,
        "approved": False,
        "g0_foundation": True,
        "certified": False,
    }


def set_budget_policy(policy: Dict[str, Any], *, persist: bool = True) -> Dict[str, Any]:
    """写入预算策略；强制重置 approved=false（须再走 approve）。

    Args:
        policy: 预算字段覆盖。
        persist: 是否落盘。

    Returns:
        回执。
    """
    global _POLICY
    base = default_budget_policy()
    base.update(dict(policy or {}))
    # 安全：改限额不能偷偷带上已批准
    base["approved"] = False
    base["approver"] = ""
    base["approved_at"] = None
    _POLICY = base
    if persist:
        path = _policy_path()
        path.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "policy": dict(base),
        "approved": False,
        "g0_foundation": True,
        "certified": False,
        "phase0_complete": False,
    }


def approve_budget(
    *,
    actor: str,
    evidence_ref: str = "",
    persist: bool = True,
) -> Dict[str, Any]:
    """人工批准预算上限。

    Args:
        actor: 批准人（必填）。
        evidence_ref: 批准证据引用。
        persist: 是否落盘。

    Returns:
        回执；无 actor 则失败。
    """
    global _POLICY
    act = str(actor or "").strip()
    out: Dict[str, Any] = {
        "ok": False,
        "approved": False,
        "error": "",
        "g0_foundation": True,
        "certified": False,
        "phase0_complete": False,
    }
    if not act:
        out["error"] = "actor_required"
        return out
    cur = get_budget_policy()["policy"]
    cur["approved"] = True
    cur["approver"] = act
    cur["approved_at"] = time.time()
    cur["evidence_ref"] = str(evidence_ref or "")
    _POLICY = cur
    if persist:
        path = _policy_path()
        path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    out.update({"ok": True, "approved": True, "policy": dict(cur)})
    return out


def check_budget(usage: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """对照硬上限检查用量；超限 ok=false。

    Args:
        usage: 当前用量（candidates/generations/llm_calls/tokens/wall_time_sec/cost_usd）。

    Returns:
        回执含 violations；未批准时另标 budget_not_approved。
    """
    pol = get_budget_policy()["policy"]
    u = dict(usage or {})
    keys = (
        ("candidates", "max_candidates"),
        ("generations", "max_generations"),
        ("llm_calls", "max_llm_calls"),
        ("tokens", "max_tokens"),
        ("wall_time_sec", "max_wall_time_sec"),
        ("cost_usd", "max_cost_usd"),
    )
    violations = []
    for uk, pk in keys:
        used = float(u.get(uk) or 0)
        lim = float(pol.get(pk) or 0)
        if used > lim:
            violations.append({"metric": uk, "used": used, "limit": lim})
    approved = bool(pol.get("approved"))
    return {
        "ok": len(violations) == 0,
        "within_budget": len(violations) == 0,
        "approved": approved,
        "budget_not_approved": not approved,
        "violations": violations,
        "policy_id": pol.get("policy_id"),
        "g0_foundation": True,
        "certified": False,
        "auto_stop": len(violations) > 0,
    }


def clear_budget_for_tests() -> None:
    """测试用：清空进程内预算策略。"""
    global _POLICY
    _POLICY = None
