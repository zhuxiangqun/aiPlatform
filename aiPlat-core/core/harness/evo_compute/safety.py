"""演化安全边界（实施计划 §11）。

默认未签字（signed=false）；须人工 sign_safety_boundary 后才算 G0 安全条件。
沙箱无生产写、须 Human Gate、禁绕过 PolicyGate。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

_BOUNDARY: Optional[Dict[str, Any]] = None


def _boundary_path() -> Path:
    """安全边界落盘路径。"""
    import tempfile

    root = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    p = Path(root) / "evo_compute" / "safety"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p / "boundary.json"
    except OSError:
        p = Path(tempfile.gettempdir()) / "aiplat_evo_compute" / "safety"
        p.mkdir(parents=True, exist_ok=True)
        return p / "boundary.json"


def default_safety_boundary() -> Dict[str, Any]:
    """默认安全边界声明（未签字）。

    Returns:
        边界字典；``signed`` 恒 False 直至人工签字。
    """
    return {
        "boundary_id": "evo_safety_g0_v1",
        "rules": [
            "sandbox_no_production_write",
            "policy_gate_required",
            "tenant_isolation",
            "human_gate_before_approved",
            "canary_before_production",
            "rollback_plan_required",
            "audit_trail_required",
        ],
        "excluded_targets": [
            "prompt_full_text",
            "policy_gate_rules",
            "core_python_code",
            "customer_contract_params",
        ],
        "signed": False,
        "signer": "",
        "signed_at": None,
        "evidence_ref": "",
    }


def get_safety_boundary() -> Dict[str, Any]:
    """读取当前安全边界（内存 → 磁盘 → 默认）。

    Returns:
        含 boundary 与 ok 的回执。
    """
    global _BOUNDARY
    if _BOUNDARY is not None:
        return {
            "ok": True,
            "boundary": dict(_BOUNDARY),
            "signed": bool(_BOUNDARY.get("signed")),
            "g0_foundation": True,
            "certified": False,
        }
    path = _boundary_path()
    data = None
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # 损坏落盘回退默认边界；不抬高 signed
            data = None
            _ = exc
    if isinstance(data, dict):
        _BOUNDARY = data
        return {
            "ok": True,
            "boundary": dict(data),
            "signed": bool(data.get("signed")),
            "g0_foundation": True,
            "certified": False,
        }
    b = default_safety_boundary()
    return {
        "ok": True,
        "boundary": b,
        "signed": False,
        "g0_foundation": True,
        "certified": False,
    }


def sign_safety_boundary(
    *,
    actor: str,
    evidence_ref: str = "",
    persist: bool = True,
) -> Dict[str, Any]:
    """安全/SRE 人工签字批准安全边界。

    Args:
        actor: 签字人（必填）。
        evidence_ref: 签字证据。
        persist: 是否落盘。

    Returns:
        回执；无 actor 则失败。
    """
    global _BOUNDARY
    act = str(actor or "").strip()
    out: Dict[str, Any] = {
        "ok": False,
        "signed": False,
        "error": "",
        "g0_foundation": True,
        "certified": False,
        "phase0_complete": False,
    }
    if not act:
        out["error"] = "actor_required"
        return out
    cur = get_safety_boundary()["boundary"]
    cur["signed"] = True
    cur["signer"] = act
    cur["signed_at"] = time.time()
    cur["evidence_ref"] = str(evidence_ref or "")
    _BOUNDARY = cur
    if persist:
        path = _boundary_path()
        path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    out.update({"ok": True, "signed": True, "boundary": dict(cur)})
    return out


def evaluate_safety_readiness() -> Dict[str, Any]:
    """安全边界就绪检查：须已签字。

    Returns:
        ready 仅在 signed=true 时为真；不宣称 phase0_complete。
    """
    g = get_safety_boundary()
    signed = bool(g.get("signed"))
    return {
        "ok": True,
        "ready": signed,
        "signed": signed,
        "boundary_id": (g.get("boundary") or {}).get("boundary_id"),
        "g0_foundation": True,
        "certified": False,
        "phase0_complete": False,
    }


def clear_safety_for_tests() -> None:
    """测试用：清空进程内安全边界。"""
    global _BOUNDARY
    _BOUNDARY = None
