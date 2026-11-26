"""生产候选 HUMAN_GATE 覆盖审计（Phase 3 / G3）。

对候选清单核算是否 100% 经 HUMAN_GATE 批准（含 actor + evidence）。
非目标：不写生产、不替代状态机、不宣称 G3 完成；夹具 ≠ 生产流量审计。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.harness.evo_compute.status import normalize_status

# 视为「生产路径」的状态：须已走过 human_gate→approved
_PRODUCTION_PATH_STATUSES = frozenset(
    {"approved", "canary", "production", "retired", "rolled_back"}
)


def default_candidate_audit_fixture() -> List[Dict[str, Any]]:
    """夹具：两例过门 + 一例缺失（用于负例）。"""
    return [
        {
            "candidate_id": "cand-a",
            "status": "production",
            "human_gate_passed": True,
            "human_gate_actor": "owner-a",
            "human_gate_evidence_ref": "hg:a",
        },
        {
            "candidate_id": "cand-b",
            "status": "canary",
            "human_gate_passed": True,
            "human_gate_actor": "owner-b",
            "human_gate_evidence_ref": "hg:b",
        },
        {
            "candidate_id": "cand-c",
            "status": "approved",
            "human_gate_passed": False,
            "human_gate_actor": "",
            "human_gate_evidence_ref": "",
        },
    ]


def default_full_coverage_fixture() -> List[Dict[str, Any]]:
    """夹具：全部生产路径候选均已 HUMAN_GATE。"""
    return [
        {
            "candidate_id": "cand-ok-1",
            "status": "production",
            "human_gate_passed": True,
            "human_gate_actor": "owner-1",
            "human_gate_evidence_ref": "hg:1",
        },
        {
            "candidate_id": "cand-ok-2",
            "status": "rolled_back",
            "human_gate_passed": True,
            "human_gate_actor": "owner-2",
            "human_gate_evidence_ref": "hg:2",
        },
    ]


def _row_passed(row: Dict[str, Any]) -> bool:
    if not bool(row.get("human_gate_passed")):
        return False
    actor = str(row.get("human_gate_actor") or "").strip()
    evid = str(row.get("human_gate_evidence_ref") or "").strip()
    return bool(actor) and bool(evid)


def audit_human_gate_coverage(
    candidates: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    require_production_path_only: bool = True,
    source: str = "fixture",
) -> Dict[str, Any]:
    """审计候选是否 100% 经 HUMAN_GATE。

    Args:
        candidates: 候选行（status / human_gate_*）；空且 source=fixture 时用全覆盖夹具。
        require_production_path_only: 仅审计已进入批准后路径的候选。
        source: ``fixture`` | ``ledger`` | ``live``（调用方标注；不伪造）。

    Returns:
        ``human_gate_100`` 等；``g3_complete`` 恒 false；夹具 ≠ 生产宣称。
    """
    src = str(source or "fixture").strip().lower() or "fixture"
    if candidates is None and src == "fixture":
        rows = [dict(r) for r in default_full_coverage_fixture()]
    else:
        rows = [dict(r) for r in (candidates or [])]
    scoped: List[Dict[str, Any]] = []
    for r in rows:
        st = normalize_status(str(r.get("status") or ""))
        if require_production_path_only and st not in _PRODUCTION_PATH_STATUSES:
            continue
        scoped.append({**r, "status": st})

    if not scoped:
        return {
            "ok": True,
            "human_gate_100": False,
            "coverage_ratio": 0.0,
            "audited": 0,
            "passed": 0,
            "missing": ["empty_production_path_set"],
            "failures": [],
            "source": src,
            "g3_foundation": True,
            "g3_complete": False,
            "certified": False,
            "e2_claimed": False,
            "production_write": False,
            "note": "no production-path candidates; cannot claim 100%",
        }

    failures: List[Dict[str, Any]] = []
    passed_n = 0
    for r in scoped:
        if _row_passed(r):
            passed_n += 1
        else:
            failures.append(
                {
                    "candidate_id": r.get("candidate_id"),
                    "status": r.get("status"),
                    "reason": "missing_human_gate_actor_or_evidence"
                    if bool(r.get("human_gate_passed"))
                    else "human_gate_not_passed",
                }
            )

    total = len(scoped)
    ratio = float(passed_n) / float(total) if total else 0.0
    full = passed_n == total and total > 0
    note = (
        "ledger candidate audit; ≠ production traffic claim"
        if src == "ledger"
        else "offline candidate audit; fixture ≠ production traffic claim"
        if src == "fixture"
        else "live-labeled candidate audit; still ≠ gate/e2 claim"
    )
    return {
        "ok": True,
        "human_gate_100": full,
        "coverage_ratio": round(ratio, 6),
        "audited": total,
        "passed": passed_n,
        "missing": [] if full else [f["candidate_id"] for f in failures],
        "failures": failures,
        "source": src,
        "g3_foundation": True,
        "g3_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
        "note": note,
    }


def audit_human_gate_from_ledger(
    *,
    require_production_path_only: bool = True,
) -> Dict[str, Any]:
    """从候选台账审计 HUMAN_GATE 覆盖。

    Args:
        require_production_path_only: 仅生产路径状态。
    """
    from core.harness.evo_compute.candidate_ledger import list_production_path_candidates

    listed = list_production_path_candidates(
        production_path_only=require_production_path_only
    )
    return audit_human_gate_coverage(
        listed.get("candidates") or [],
        require_production_path_only=require_production_path_only,
        source="ledger",
    )
