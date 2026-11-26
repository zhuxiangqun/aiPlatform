"""评测 Operational E10–E12：授权门 + 双人 κ（默认未授权；≠ certified）。

E10 ``process_split`` / E11 生产 SLA 须非作者批准记录才可能 ``authorized=true``；
环境变量单独打开 MUST NOT 解锁。E12 可生成 κ 报告，但仍 ``accuracy_claim=false``。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _load_approval_record(path: Optional[str]) -> Optional[Dict[str, Any]]:
    """读取批准 JSON；缺文件/坏 JSON → None。

    Args:
        path: 批准记录路径。
    """
    if not path or not str(path).strip():
        return None
    p = Path(str(path).strip()).expanduser()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _approval_ok(
    rec: Optional[Dict[str, Any]],
    *,
    expected_scope: str,
) -> Tuple[bool, str]:
    """非作者批准记录是否足以开闸。

    Args:
        rec: 批准记录。
        expected_scope: 期望 scope 子串（如 ``E10`` / ``eval-operational``）。
    """
    if not rec:
        return False, "approval_record_missing"
    status = str(rec.get("status") or "").strip().lower()
    if status not in {"approved", "authorize", "authorized"}:
        return False, f"approval_status_not_approved:{status or 'empty'}"
    decision = str(rec.get("decision") or "").strip().lower()
    if decision and decision not in {"approve", "approved", "authorize"}:
        return False, f"approval_decision_denied:{decision}"
    approvers = rec.get("approvers") or []
    if not isinstance(approvers, list) or not [a for a in approvers if str(a).strip()]:
        return False, "approvers_empty"
    scope = str(rec.get("scope") or rec.get("gate_ids") or "").lower()
    if expected_scope and expected_scope.lower() not in scope:
        # 也允许 gate_ids 列表
        gates = rec.get("gate_ids") if isinstance(rec.get("gate_ids"), list) else []
        if expected_scope not in {str(g) for g in gates}:
            return False, f"scope_mismatch:need_{expected_scope}"
    return True, "ok"


def evaluate_eval_process_split_authorize(
    *,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """E10：A3 process_split 授权门（默认 false）。

    Args:
        approval_record_path: 非作者批准 JSON。
    """
    env_claim = str(os.environ.get("AIPLAT_EVAL_PROCESS_SPLIT_AUTHORIZED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    rec = _load_approval_record(approval_record_path)
    ok, reason = _approval_ok(rec, expected_scope="E10")
    # 环境变量宣称不得单独解锁
    authorized = bool(ok)
    return {
        "schema": "aiplat.eval.operational.e10.v0",
        "gate_id": "E10",
        "authorized": authorized,
        "process_split_authorized": authorized,
        "process_split_policy_env_claimed": env_claim,
        "env_alone_insufficient": True,
        "reason": reason if not authorized else "approved",
        "approval_present": rec is not None,
        "honesty": "E10 gate exists; default unauthorized; env≠unlock; ≠ certified",
    }


def evaluate_eval_production_sla_authorize(
    *,
    approval_record_path: Optional[str] = None,
    sla_ref: str = "",
) -> Dict[str, Any]:
    """E11：生产 SLA / authorize 门（默认 false）。

    Args:
        approval_record_path: 非作者批准 JSON。
        sla_ref: 可选 SLA 引用；批准通过时建议非空。
    """
    rec = _load_approval_record(approval_record_path)
    ok, reason = _approval_ok(rec, expected_scope="E11")
    sla = str(sla_ref or (rec or {}).get("sla_ref") or "").strip()
    if ok and not sla:
        ok = False
        reason = "sla_ref_required"
    return {
        "schema": "aiplat.eval.operational.e11.v0",
        "gate_id": "E11",
        "authorized": bool(ok),
        "production_authorize": bool(ok),
        "sla_ref": sla or None,
        "reason": reason if not ok else "approved",
        "approval_present": rec is not None,
        "honesty": "E11 production SLA authorize; default false; ≠ accuracy",
    }


def build_dual_annotator_kappa_report(
    pairs: Optional[Sequence[Tuple[bool, bool]]] = None,
    *,
    scope: str = "",
    annotator_a: str = "annotator_a",
    annotator_b: str = "annotator_b",
) -> Dict[str, Any]:
    """E12：双人标注 κ 报告（Cohen；``accuracy_claim=false``）。

    Args:
        pairs: ``(label_a_pass, label_b_pass)`` 序列。
        scope: 对象/域/版本范围说明。
        annotator_a: 标注者 A。
        annotator_b: 标注者 B。
    """
    from core.apps.eval.service.g2c import cohen_kappa_binary

    raw = cohen_kappa_binary(list(pairs or []))
    kappa = raw.get("intra_rater_kappa")
    return {
        "schema": "aiplat.eval.dual_annotator_kappa.v0",
        "gate_id": "E12",
        "kappa_kind": "inter_annotator",
        "inter_annotator_kappa": kappa,
        "n": raw.get("n"),
        "agreement": raw.get("agreement"),
        "chance_agreement": raw.get("chance_agreement"),
        "confusion": raw.get("confusion"),
        "scope": str(scope or "").strip() or None,
        "annotators": [annotator_a, annotator_b],
        "accuracy_claim": False,
        "claim_eligible": False,
        "honesty": (
            "E12 dual-annotator κ ≠ accuracy / ≠ G2c intra-rater; "
            "appendix O still required for external accuracy claims"
        ),
    }


def evaluate_eval_operational_bundle(
    *,
    approval_record_path: Optional[str] = None,
    sla_ref: str = "",
    kappa_pairs: Optional[Sequence[Tuple[bool, bool]]] = None,
) -> Dict[str, Any]:
    """汇总 E10–E12 测量态（全部 authorized 才 operational_ready）。

    Args:
        approval_record_path: 可含 E10/E11 的批准（scope 须匹配各项）。
        sla_ref: E11 SLA。
        kappa_pairs: E12 可选成对标签。
    """
    e10 = evaluate_eval_process_split_authorize(
        approval_record_path=approval_record_path
    )
    e11 = evaluate_eval_production_sla_authorize(
        approval_record_path=approval_record_path, sla_ref=sla_ref
    )
    e12 = build_dual_annotator_kappa_report(kappa_pairs)
    ready = bool(e10.get("authorized") and e11.get("authorized"))
    return {
        "schema": "aiplat.eval.operational.bundle.v0",
        "E10": e10,
        "E11": e11,
        "E12": e12,
        "operational_ready": ready,
        "honesty": "bundle measurement; operational_ready requires E10+E11 approval; ≠ certified",
    }
