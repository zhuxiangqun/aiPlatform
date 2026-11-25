"""Candidate.status 状态机（演化架构 §6 SSOT）。

合法枚举与变迁；禁止 ``evaluated``；APPROVED ≠ SAFETY_PASSED。
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional, Tuple

# 架构 §6 逐字对齐（小写存储）
CANDIDATE_STATUSES: FrozenSet[str] = frozenset(
    {
        "draft",
        "registered",
        "evaluating",
        "ranked",
        "safety_passed",
        "human_gate",
        "approved",
        "rejected",
        "canary",
        "production",
        "retired",
        "rolled_back",
    }
)

# 有向边：from → allowed tos
_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "draft": frozenset({"registered", "rejected"}),
    "registered": frozenset({"evaluating", "rejected"}),
    "evaluating": frozenset({"ranked", "rejected"}),
    "ranked": frozenset({"safety_passed", "rejected"}),
    "safety_passed": frozenset({"human_gate", "rejected"}),
    "human_gate": frozenset({"approved", "rejected"}),
    "approved": frozenset({"canary", "rejected"}),
    "canary": frozenset({"production", "rolled_back", "rejected"}),
    "production": frozenset({"retired", "rolled_back"}),
    "rejected": frozenset({"retired"}),
    "rolled_back": frozenset({"retired"}),
    "retired": frozenset(),
}

_ABOLISHED = frozenset({"evaluated"})


def normalize_status(status: str) -> str:
    """规范化状态字符串。

    Args:
        status: 原始状态。

    Returns:
        小写去空白状态。
    """
    return str(status or "").strip().lower()


def is_legal_status(status: str) -> bool:
    """是否为合法 Candidate.status。

    Args:
        status: 状态字符串。
    """
    s = normalize_status(status)
    return s in CANDIDATE_STATUSES and s not in _ABOLISHED


def can_transition(from_status: str, to_status: str) -> bool:
    """是否允许状态变迁。

    Args:
        from_status: 当前状态。
        to_status: 目标状态。
    """
    fr = normalize_status(from_status)
    to = normalize_status(to_status)
    if not is_legal_status(fr) or not is_legal_status(to):
        return False
    return to in _TRANSITIONS.get(fr, frozenset())


def advance_candidate_status(
    *,
    candidate_id: str,
    from_status: str,
    to_status: str,
    actor: str,
    evidence_ref: str = "",
    version: str = "1",
) -> Dict[str, Any]:
    """推进候选状态；非法变迁失败关闭。

    Args:
        candidate_id: 候选 id。
        from_status: 当前状态。
        to_status: 目标状态。
        actor: 操作者（人工或 system_policy）。
        evidence_ref: 证据引用。
        version: 版本号。

    Returns:
        回执含 ``ok`` / ``status`` / ``error``。
    """
    cid = str(candidate_id or "").strip()
    fr = normalize_status(from_status)
    to = normalize_status(to_status)
    act = str(actor or "").strip()
    out: Dict[str, Any] = {
        "ok": False,
        "candidate_id": cid,
        "from_status": fr,
        "to_status": to,
        "actor": act,
        "evidence_ref": str(evidence_ref or ""),
        "version": str(version or "1"),
        "status": fr,
        "error": "",
        "g0_foundation": True,
        "certified": False,
        "e2_claimed": False,
    }
    if not cid:
        out["error"] = "candidate_id_required"
        return out
    if not act:
        out["error"] = "actor_required"
        return out
    if to in _ABOLISHED or fr in _ABOLISHED:
        out["error"] = "abolished_status_evaluated"
        return out
    if not is_legal_status(fr):
        out["error"] = "illegal_from_status"
        return out
    if not is_legal_status(to):
        out["error"] = "illegal_to_status"
        return out
    if not can_transition(fr, to):
        out["error"] = "illegal_transition"
        return out
    # 进入 approved：必须经过 human_gate（调用方 from 必须是 human_gate）
    if to == "approved" and fr != "human_gate":
        out["error"] = "approved_requires_human_gate"
        return out
    out["ok"] = True
    out["status"] = to
    return out


def default_happy_path() -> Tuple[str, ...]:
    """低风险试点默认幸福路径（含显式 human_gate）。"""
    return (
        "draft",
        "registered",
        "evaluating",
        "ranked",
        "safety_passed",
        "human_gate",
        "approved",
        "canary",
        "production",
    )
