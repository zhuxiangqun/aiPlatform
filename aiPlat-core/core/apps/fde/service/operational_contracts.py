"""FDE Operational F10–F11：生产独立进程 authorize / compose 长驻（默认未授权）。

本模块不扩大 ADR-09：无非作者批准时恒 ``authorized=false``。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


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
    """校验批准记录。

    Args:
        rec: 记录。
        gate_id: ``F10`` / ``F11``。
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


def evaluate_fde_production_process_authorize(
    *,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """F10：生产独立进程 authorize（默认 false）。

    Args:
        approval_record_path: 非作者批准 JSON。
    """
    env_claim = str(os.environ.get("AIPLAT_FDE_OPTIONAL_SPLIT") or "").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }
    rec = _load_approval(approval_record_path)
    ok, reason = _approval_ok(rec, "F10")
    return {
        "schema": "aiplat.fde.operational.f10.v0",
        "gate_id": "F10",
        "authorized": bool(ok),
        "production_process_authorize": bool(ok),
        "optional_split_env_claimed": env_claim,
        "env_alone_insufficient": True,
        "reason": reason if not ok else "approved",
        "honesty": "F10: one-shot health ≠ production authorize; ADR-09 unchanged",
    }


def evaluate_fde_compose_long_running_authorize(
    *,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """F11：compose 长驻授权（须另批 ADR；默认 false）。

    Args:
        approval_record_path: 须含 F11 + 另批 ADR 引用。
    """
    rec = _load_approval(approval_record_path)
    ok, reason = _approval_ok(rec, "F11")
    adr_ref = str((rec or {}).get("adr_ref") or "").strip()
    if ok and not adr_ref:
        ok = False
        reason = "adr_ref_required_for_compose_long_running"
    return {
        "schema": "aiplat.fde.operational.f11.v0",
        "gate_id": "F11",
        "authorized": bool(ok),
        "compose_long_running_authorized": bool(ok),
        "adr_ref": adr_ref or None,
        "reason": reason if not ok else "approved",
        "honesty": "F11 never default-on; standard appendix does not authorize compose long-run",
    }


def evaluate_fde_operational_bundle(
    *,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """汇总 F10–F11。

    Args:
        approval_record_path: 批准路径。
    """
    f10 = evaluate_fde_production_process_authorize(
        approval_record_path=approval_record_path
    )
    f11 = evaluate_fde_compose_long_running_authorize(
        approval_record_path=approval_record_path
    )
    return {
        "schema": "aiplat.fde.operational.bundle.v0",
        "F10": f10,
        "F11": f11,
        "operational_ready": bool(f10.get("authorized") and f11.get("authorized")),
        "honesty": "operational_ready rare; F11 needs separate ADR; ≠ certified",
    }
