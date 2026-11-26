"""生产加深 D4：活台账 HITL 100% + 已测 L4/缓释签批包。

组装 ledger 审计与闭环 L4 报告；owner 可签批 deepen pack。
``d4_signed`` ≠ Gate/E2 完成；``g*_complete`` / ``certified`` / ``e2_claimed`` 恒 false。
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from core.harness.evo_compute.human_gate_audit import audit_human_gate_from_ledger
from core.harness.evo_compute.loops_l4 import build_loops_l4_assessment_report

_SIGNOFF: Optional[Dict[str, Any]] = None


def _honesty() -> Dict[str, Any]:
    return {
        "g3_foundation": True,
        "g3_complete": False,
        "g2_complete": False,
        "g1_complete": False,
        "certified": False,
        "e2_claimed": False,
        "production_write": False,
    }


def _signoff_path() -> Path:
    """D4 签批落盘路径。"""
    root = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    p = Path(root) / "evo_compute"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p / "deepen_d4_signoff.json"
    except OSError:
        p = Path(tempfile.gettempdir()) / "aiplat_evo_compute"
        p.mkdir(parents=True, exist_ok=True)
        return p / "deepen_d4_signoff.json"


def clear_d4_signoff_for_tests() -> None:
    """测试用：清空进程内 D4 签批状态。"""
    global _SIGNOFF
    _SIGNOFF = None


def get_production_deepen_d4_signoff() -> Dict[str, Any]:
    """读取当前 D4 签批状态（内存 → 磁盘 → 未签）。

    Returns:
        含 ``d4_signed`` 的回执；未签时 ``d4_signed=false``。
    """
    global _SIGNOFF
    if _SIGNOFF is not None:
        return {
            "ok": True,
            "d4_signed": bool(_SIGNOFF.get("d4_signed")),
            "signoff": dict(_SIGNOFF),
            **_honesty(),
        }
    path = _signoff_path()
    data: Optional[Dict[str, Any]] = None
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            data = None
    if isinstance(data, dict) and data.get("d4_signed"):
        _SIGNOFF = data
        return {
            "ok": True,
            "d4_signed": True,
            "signoff": dict(data),
            **_honesty(),
        }
    return {
        "ok": True,
        "d4_signed": False,
        "signoff": {},
        **_honesty(),
        "note": "d4 deepen pack not signed",
    }


def collect_production_deepen_d4_pack(
    *,
    levels: Optional[Dict[str, Any]] = None,
    measured: bool = False,
    waiver_owner: str = "",
    waiver_signed: bool = False,
    waiver_gap_list: Optional[Sequence[str]] = None,
    require_production_path_only: bool = True,
    hitl_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """组装活台账 HITL + 闭环 L4/缓释 deepen 包（未签批）。

    Args:
        levels: 四闭环等级；None 时 L4 报告用默认夹具且 measured 须由调用方标明。
        measured: 是否真实测量等级（夹具须 false）。
        waiver_owner: 缓释 owner。
        waiver_signed: 缓释是否已签字。
        waiver_gap_list: 差距清单。
        require_production_path_only: 仅审计生产路径候选。
        hitl_audit: 可选预计算 HITL 审计；缺则从台账拉取。
    """
    hitl = (
        dict(hitl_audit)
        if isinstance(hitl_audit, dict)
        else audit_human_gate_from_ledger(
            require_production_path_only=require_production_path_only
        )
    )
    # 夹具 levels 不得冒充 measured
    use_measured = bool(measured)
    if levels is None and not use_measured:
        # 未注入 levels：诚实不可用（不默认夹具冒充 live）
        l4 = build_loops_l4_assessment_report(
            levels={"governance": 0, "knowledge": 0, "eval": 0, "fde": 0},
            measured=False,
            waiver_owner=waiver_owner,
            waiver_signed=waiver_signed,
            waiver_gap_list=waiver_gap_list,
        )
        l4["source"] = "unavailable"
        l4["baseline_missing"] = True
    else:
        l4 = build_loops_l4_assessment_report(
            levels=levels,
            measured=use_measured,
            waiver_owner=waiver_owner,
            waiver_signed=waiver_signed,
            waiver_gap_list=waiver_gap_list,
        )
        l4["source"] = "measured" if use_measured else "fixture_or_injected"
        l4["baseline_missing"] = not use_measured and not bool(l4.get("waiver", {}).get("valid"))

    hitl_ok = bool(hitl.get("human_gate_100")) and str(hitl.get("source") or "") in (
        "ledger",
        "live",
    )
    # fixture HITL 不算活台账 100%
    if str(hitl.get("source") or "") == "fixture":
        hitl_ok = False
    l4_ok = bool(l4.get("loops_l4_or_waiver")) and (
        use_measured or bool(l4.get("waiver", {}).get("valid"))
    )
    pack_ready = hitl_ok and l4_ok
    existing = get_production_deepen_d4_signoff()

    return {
        "ok": True,
        "slice": "production-deepen-d4",
        "hitl": hitl,
        "loops_l4": l4,
        "pack_ready": pack_ready,
        "hitl_live_100": hitl_ok,
        "loops_l4_or_waiver_ok": l4_ok,
        "d4_signed": bool(existing.get("d4_signed")),
        "missing": [
            k
            for k, v in {
                "hitl_live_100": hitl_ok,
                "loops_l4_or_waiver_ok": l4_ok,
            }.items()
            if not v
        ],
        **_honesty(),
        "note": "d4 pack assemble; pack_ready≠gate claim; d4_signed≠g3_complete",
    }


def sign_production_deepen_d4(
    *,
    actor: str,
    evidence_ref: str,
    pack: Optional[Dict[str, Any]] = None,
    levels: Optional[Dict[str, Any]] = None,
    measured: bool = False,
    waiver_owner: str = "",
    waiver_signed: bool = False,
    waiver_gap_list: Optional[Sequence[str]] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Owner 签批 D4 deepen 包；要求 ``pack_ready``。

    Args:
        actor: 签批人。
        evidence_ref: 证据引用。
        pack: 预组装包；缺则现场 collect。
        levels: 透传 collect。
        measured: 透传 collect。
        waiver_owner: 透传 collect。
        waiver_signed: 透传 collect。
        waiver_gap_list: 透传 collect。
        persist: 是否落盘签批。

    Returns:
        回执；成功时 ``d4_signed=true``；仍不宣称 Gate/E2。
    """
    global _SIGNOFF
    act = str(actor or "").strip()
    evid = str(evidence_ref or "").strip()
    out: Dict[str, Any] = {
        "ok": False,
        "d4_signed": False,
        "error": "",
        **_honesty(),
    }
    if not act or not evid:
        out["error"] = "actor_and_evidence_required"
        return out

    pack_obj = (
        dict(pack)
        if isinstance(pack, dict)
        else collect_production_deepen_d4_pack(
            levels=levels,
            measured=measured,
            waiver_owner=waiver_owner,
            waiver_signed=waiver_signed,
            waiver_gap_list=waiver_gap_list,
        )
    )
    if not pack_obj.get("pack_ready"):
        out["error"] = "pack_not_ready"
        out["missing"] = list(pack_obj.get("missing") or [])
        out["pack"] = pack_obj
        return out

    blob = {
        "schema": "aiplat.evo_deepen_d4_signoff.v1",
        "d4_signed": True,
        "actor": act,
        "evidence_ref": evid,
        "signed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pack_snapshot": {
            "hitl_live_100": bool(pack_obj.get("hitl_live_100")),
            "loops_l4_or_waiver_ok": bool(pack_obj.get("loops_l4_or_waiver_ok")),
            "hitl_source": (pack_obj.get("hitl") or {}).get("source"),
            "l4_measured": (pack_obj.get("loops_l4") or {}).get("measured"),
            "l4_waiver_valid": ((pack_obj.get("loops_l4") or {}).get("waiver") or {}).get(
                "valid"
            ),
        },
    }
    if persist:
        try:
            _signoff_path().write_text(
                json.dumps(blob, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            out["error"] = f"persist_failed:{exc}"
            out["pack"] = pack_obj
            return out

    _SIGNOFF = blob
    out["ok"] = True
    out["d4_signed"] = True
    out["signoff"] = blob
    out["pack"] = pack_obj
    out["note"] = "d4 deepen signed; still ≠ g3_complete/e2/certified"
    return out


def evaluate_production_deepen_d4_readiness(
    pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """D4 就绪评估：pack_ready + 可选已签；不抬升 Gate 宣称。

    Args:
        pack: 预组装包；缺则现场 collect（levels 缺 → L4 unavailable）。
    """
    pack_obj = dict(pack) if isinstance(pack, dict) else collect_production_deepen_d4_pack()
    signed = get_production_deepen_d4_signoff()
    ready = bool(pack_obj.get("pack_ready")) and bool(signed.get("d4_signed"))
    return {
        "ok": True,
        "ready": ready,
        "pack_ready": bool(pack_obj.get("pack_ready")),
        "d4_signed": bool(signed.get("d4_signed")),
        "missing": list(pack_obj.get("missing") or [])
        + ([] if signed.get("d4_signed") else ["d4_signed"]),
        "pack": pack_obj,
        "signoff": signed.get("signoff") or {},
        **_honesty(),
        "note": "d4 readiness; ready≠gate exit claim",
    }
