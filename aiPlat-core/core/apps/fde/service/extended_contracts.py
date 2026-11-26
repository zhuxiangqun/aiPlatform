"""FDE Extended F07–F09 契约声明（测量用；非 certified / 非 compose 长驻授权）。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def fde_slice_report_binding_policy() -> Dict[str, Any]:
    """F07：切片签收须绑定诊断 report_id 的策略说明。

    Returns:
        策略 dict；权威实现仍为 ``validate_slice_signoff_reports``。
    """
    return {
        "schema": "aiplat.fde.slice_report_binding.v0",
        "policy_id": "F07",
        "canonical_validator": "core.apps.fde.service.slice_evidence.validate_slice_signoff_reports",
        "http_entry": "POST /api/platform/apps/fde/acceptance/signoff",
        "rules": [
            "for_slice / fp-* / AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 → evidence_report_ids MUST",
            "report must exist and diagnosis status=ok (stale/fail ≠ success)",
            "GateResult / ImportReport MUST NOT substitute signoff",
        ],
        "honesty": "policy card ≠ certified delivery",
    }


def fde_workbench_signoff_surface() -> Dict[str, Any]:
    """F08：工作台完整签收面契约（AcceptTab → 唯一 signoff）。

    Returns:
        UI/API 面说明。
    """
    return {
        "schema": "aiplat.fde.workbench_signoff.v0",
        "surface_id": "F08",
        "ui": "FdeDashboard AcceptTab → POST …/acceptance/signoff",
        "checklist": "GET …/acceptance/checklist（含⑥b 预检）",
        "no_parallel_signoff_api": True,
        "evidence_refs": [
            "frontend:FdeDashboard.tsx:AcceptTab",
            "platform:apps/fde/api/fde_acceptance.py",
        ],
        "honesty": "workbench UI ≠ accuracy / ≠ eval Gate pass",
    }


def fde_optional_process_contract() -> Dict[str, Any]:
    """F09：可选独立进程文书 + one-shot health（非默认、非长驻授权）。

    Returns:
        脚本路径与诚实字段；``compose_long_running_authorized=false``。
    """
    root = Path(__file__).resolve().parents[5]
    health_py = root / "scripts" / "adr09_fde_optional_health_server.py"
    phase_sh = root / "scripts" / "adr09_fde_optional_phase_health.sh"
    return {
        "schema": "aiplat.fde.optional_process.v0",
        "contract_id": "F09",
        "default_deploy": "cohosted",
        "optional_split_env": "AIPLAT_FDE_OPTIONAL_SPLIT",
        "health_script": str(health_py) if health_py.is_file() else "scripts/adr09_fde_optional_health_server.py",
        "phase_health_script": str(phase_sh) if phase_sh.is_file() else "scripts/adr09_fde_optional_phase_health.sh",
        "scripts_exist": bool(health_py.is_file() and phase_sh.is_file()),
        "compose_long_running_authorized": False,
        "process_split_authorized": False,
        "rollback": "stop optional → cohosted → existing signoff path",
        "honesty": "F09 docs/scripts ≠ production authorize / ≠ ADR compose long-run",
    }
