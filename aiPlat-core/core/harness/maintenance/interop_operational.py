"""外援互通 Operational X10–X11：生产 authorize + 供应商 SLA（默认未授权）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def _load_approval(path: Optional[str]) -> Optional[Dict[str, Any]]:
    """读取批准 JSON。

    Args:
        path: 路径。
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


def _approval_ok(rec: Optional[Dict[str, Any]], gate_id: str) -> tuple[bool, str]:
    """校验非作者批准。

    Args:
        rec: 批准记录。
        gate_id: ``X10`` / ``X11``。
    """
    if not rec:
        return False, "approval_record_missing"
    status = str(rec.get("status") or "").strip().lower()
    if status not in {"approved", "authorize", "authorized"}:
        return False, f"approval_status_not_approved:{status or 'empty'}"
    approvers = rec.get("approvers") or []
    if not isinstance(approvers, list) or not [a for a in approvers if str(a).strip()]:
        return False, "approvers_empty"
    scope = str(rec.get("scope") or "").lower()
    gates = rec.get("gate_ids") if isinstance(rec.get("gate_ids"), list) else []
    if gate_id.lower() not in scope and gate_id not in {str(g) for g in gates}:
        return False, f"scope_mismatch:need_{gate_id}"
    return True, "ok"


def evaluate_interop_production_authorize(
    *,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """X10：外援生产 authorize（默认 false）。

    Args:
        approval_record_path: 非作者批准 JSON。
    """
    rec = _load_approval(approval_record_path)
    ok, reason = _approval_ok(rec, "X10")
    return {
        "schema": "aiplat.interop.operational.x10.v0",
        "gate_id": "X10",
        "authorized": bool(ok),
        "production_authorize": bool(ok),
        "reason": reason if not ok else "approved",
        "approval_present": rec is not None,
        "honesty": "X10 production authorize; import success ≠ authorize; default false",
    }


def bind_supplier_sla(
    compat: Optional[Mapping[str, Any]] = None,
    *,
    sla_ref: str = "",
    vendor_id: str = "",
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """X11：供应商 SLA 绑定（无 ref / 无批准 → 未绑定）。

    Args:
        compat: 可选 COMPAT 片段（只读增强到返回值）。
        sla_ref: SLA 文档/合同引用。
        vendor_id: 供应商 ID。
        approval_record_path: 非作者批准（生产绑定须批准）。
    """
    rec = _load_approval(approval_record_path)
    ok, reason = _approval_ok(rec, "X11")
    ref = str(sla_ref or (rec or {}).get("sla_ref") or "").strip()
    vendor = str(vendor_id or (rec or {}).get("vendor_id") or "").strip()
    bound = bool(ok and ref)
    if ok and not ref:
        reason = "sla_ref_required"
        bound = False
    out_compat = dict(compat or {})
    if bound:
        out_compat["supplier_sla"] = {
            "sla_ref": ref,
            "vendor_id": vendor or None,
            "bound": True,
        }
    return {
        "schema": "aiplat.interop.operational.x11.v0",
        "gate_id": "X11",
        "bound": bound,
        "authorized": bound,
        "sla_ref": ref or None,
        "vendor_id": vendor or None,
        "reason": reason if not bound else "approved",
        "compat": out_compat,
        "honesty": "X11 SLA bind requires approval+sla_ref; ≠ L2 auto-grant",
    }


def evaluate_interop_operational_bundle(
    *,
    approval_record_path: Optional[str] = None,
    sla_ref: str = "",
    vendor_id: str = "",
) -> Dict[str, Any]:
    """汇总 X10–X11。

    Args:
        approval_record_path: 批准路径。
        sla_ref: SLA。
        vendor_id: 供应商。
    """
    x10 = evaluate_interop_production_authorize(
        approval_record_path=approval_record_path
    )
    x11 = bind_supplier_sla(
        sla_ref=sla_ref,
        vendor_id=vendor_id,
        approval_record_path=approval_record_path,
    )
    return {
        "schema": "aiplat.interop.operational.bundle.v0",
        "X10": x10,
        "X11": x11,
        "operational_ready": bool(x10.get("authorized") and x11.get("bound")),
        "honesty": "operational_ready needs X10+X11; ≠ certified",
    }
