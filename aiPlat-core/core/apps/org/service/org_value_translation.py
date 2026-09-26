"""H3 — value translation. Read-only. Not a second KPI engine. Not a signature."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

_CLOSED = frozenset({"succeeded", "completed", "completed_partial"})
_SOURCES = frozenset({"customer_provided", "platform_default", "missing"})


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _safe_tenant(tenant_id: str) -> str:
    tid = (tenant_id or "").strip()
    if not tid or ".." in tid or "/" in tid or "\\" in tid:
        return ""
    return tid


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning("value baseline unreadable %s: %s", path, e)
        return None
    return raw if isinstance(raw, dict) else None


def load_value_baseline(*, tenant_id: str = "") -> Dict[str, Any]:
    """Tenant-isolated baseline. Never reads another tenant's file."""
    tid = _safe_tenant(tenant_id)
    if tid:
        cust = _load_yaml(_home() / "org" / "tenants" / tid / "value_baseline.yaml")
        if cust is not None:
            return {
                "baseline_source": "customer_provided",
                "tenant_id": tid,
                "baseline_minutes_per_incident": cust.get("baseline_minutes_per_incident"),
                "baseline_mtta_seconds": cust.get("baseline_mtta_seconds"),
                "path": f"org/tenants/{tid}/value_baseline.yaml",
            }

    plat = _load_yaml(_home() / "org" / "value_baseline.yaml")
    if plat is not None:
        return {
            "baseline_source": "platform_default",
            "tenant_id": tid or None,
            "baseline_minutes_per_incident": plat.get("baseline_minutes_per_incident"),
            "baseline_mtta_seconds": plat.get("baseline_mtta_seconds"),
            "path": "org/value_baseline.yaml",
        }

    return {
        "baseline_source": "missing",
        "tenant_id": tid or None,
        "baseline_minutes_per_incident": None,
        "baseline_mtta_seconds": None,
        "path": None,
    }


def _closed_run_count(runs: list) -> int:
    n = 0
    for r in runs:
        if not isinstance(r, dict):
            continue
        if str(r.get("status") or "") in _CLOSED:
            n += 1
    return n


def translate_org_value(
    *,
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    week: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    """Audit-friendly value card from weekly KPI + baseline. Never invents savings."""
    from core.apps.org.service.org_kpi import weekly_kpi_report
    from core.apps.org.service.org_runtime import list_runs

    did = (domain_id or "").strip() or "it-ops"
    gid = (goal_id or "").strip() or "goal-it-ops-alert-sla"
    weekly = weekly_kpi_report(did, gid, week=week or "")
    runs = list_runs(gid, limit=50).get("runs") or []
    week_f = (week or "").strip()
    if week_f:
        runs = [r for r in runs if str(r.get("week_label") or "") == week_f]

    closed = _closed_run_count(runs)
    kpis = weekly.get("kpis") or {}
    current_mtta = kpis.get("mtta_seconds")

    baseline = load_value_baseline(tenant_id=tenant_id)
    source = baseline.get("baseline_source") or "missing"
    if source not in _SOURCES:
        source = "missing"

    minutes = baseline.get("baseline_minutes_per_incident")
    base_mtta = baseline.get("baseline_mtta_seconds")
    baseline_missing = source == "missing"

    saved_person_hours = None
    mtta_delta_seconds = None
    formula_notes = []

    if not baseline_missing and minutes is not None:
        try:
            m = float(minutes)
            if m >= 0:
                saved_person_hours = round(closed * m / 60.0, 4)
                formula_notes.append(
                    f"saved_person_hours = {closed} × {m} / 60"
                )
        except (TypeError, ValueError):
            formula_notes.append("baseline_minutes_per_incident 无法解析")
    else:
        formula_notes.append("无基线：不显示节省人时")

    if (
        not baseline_missing
        and base_mtta is not None
        and current_mtta is not None
    ):
        try:
            mtta_delta_seconds = float(base_mtta) - float(current_mtta)
            formula_notes.append(
                f"mtta_delta_seconds = {base_mtta} − {current_mtta}"
            )
        except (TypeError, ValueError):
            formula_notes.append("mtta 基线或当前值无法解析")
    elif baseline_missing or base_mtta is None:
        formula_notes.append("无 MTTA 基线：不显示缩短量")
    elif current_mtta is None:
        formula_notes.append("当前 MTTA 缺失：不显示缩短量")

    platform_kpis = {
        "mtta_seconds": current_mtta,
        "root_cause_rate": kpis.get("root_cause_rate"),
        "exception_ratio": kpis.get("exception_ratio"),
        "run_count": weekly.get("run_count"),
        "closed_runs": closed,
    }

    return {
        "ok": True,
        "writable": False,
        "layer": "value_translation",
        "m4_claim_allowed": False,
        "signoff_button": False,
        "domain_id": did,
        "goal_id": gid,
        "week": week_f or None,
        "tenant_id": baseline.get("tenant_id"),
        "baseline_source": source,
        "baseline_missing": baseline_missing,
        "baseline": {
            "minutes_per_incident": None if baseline_missing else minutes,
            "mtta_seconds": None if baseline_missing else base_mtta,
            "path": baseline.get("path"),
        },
        "platform_kpis": platform_kpis,
        "saved_person_hours": None if baseline_missing else saved_person_hours,
        "mtta_delta_seconds": None if baseline_missing else mtta_delta_seconds,
        "formula_notes": formula_notes,
        "authority_note": (
            "可审计收益翻译，不是签收。禁止准确率口号。"
            "无基线不编节省人时。"
        ),
    }


def preview_value_roi(
    *,
    domain_id: str = "it-ops",
    goal_id: str = "goal-it-ops-alert-sla",
    week: str = "",
    trial_minutes_per_incident: float,
    trial_mtta_seconds: float,
) -> Dict[str, Any]:
    """What-if ROI. Never writes baseline; never claims customer savings."""
    from core.apps.org.service.org_kpi import weekly_kpi_report
    from core.apps.org.service.org_runtime import list_runs

    try:
        minutes = float(trial_minutes_per_incident)
        base_mtta = float(trial_mtta_seconds)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "reason": "trial_invalid",
            "writable": False,
            "simulation": True,
            "m4_claim_allowed": False,
        }
    if minutes < 0 or base_mtta < 0:
        return {
            "ok": False,
            "reason": "trial_negative",
            "writable": False,
            "simulation": True,
            "m4_claim_allowed": False,
        }

    did = (domain_id or "").strip() or "it-ops"
    gid = (goal_id or "").strip() or "goal-it-ops-alert-sla"
    weekly = weekly_kpi_report(did, gid, week=week or "")
    runs = list_runs(gid, limit=50).get("runs") or []
    week_f = (week or "").strip()
    if week_f:
        runs = [r for r in runs if str(r.get("week_label") or "") == week_f]
    closed = _closed_run_count(runs)
    kpis = weekly.get("kpis") or {}
    current_mtta = kpis.get("mtta_seconds")

    saved = round(closed * minutes / 60.0, 4)
    formula_notes = [
        f"what_if: saved_person_hours = {closed} × {minutes} / 60",
        "试算不是客户基线；写入基线后才出现在价值卡。",
    ]
    mtta_delta = None
    if current_mtta is not None:
        try:
            mtta_delta = base_mtta - float(current_mtta)
            formula_notes.append(
                f"what_if: mtta_delta_seconds = {base_mtta} − {current_mtta}"
            )
        except (TypeError, ValueError):
            formula_notes.append("当前 MTTA 无法解析")
    else:
        formula_notes.append("当前 MTTA 缺失：不显示缩短量")

    return {
        "ok": True,
        "writable": False,
        "simulation": True,
        "layer": "value_roi_preview",
        "baseline_source": "what_if",
        "baseline_missing": True,
        "m4_claim_allowed": False,
        "signoff_button": False,
        "wrote_baseline": False,
        "domain_id": did,
        "goal_id": gid,
        "week": week_f or None,
        "trial": {
            "minutes_per_incident": minutes,
            "mtta_seconds": base_mtta,
        },
        "platform_kpis": {
            "mtta_seconds": current_mtta,
            "closed_runs": closed,
            "run_count": weekly.get("run_count"),
        },
        "saved_person_hours": saved,
        "mtta_delta_seconds": mtta_delta,
        "formula_notes": formula_notes,
        "authority_note": (
            "试算仅供填写引导。不是客户基线，不是签收，不写入磁盘。"
            "m4_claim_allowed 恒 false。"
        ),
    }


def save_value_baseline(
    *,
    role: str,
    tenant_id: str,
    baseline_minutes_per_incident: float,
    baseline_mtta_seconds: float,
) -> Dict[str, Any]:
    """S2: write tenant baseline. Never invents; never flips m4_claim_allowed."""
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "writable": False}
    if role_n not in ("admin", "operator"):
        return {"ok": False, "reason": "write_forbidden", "writable": False}
    tid = _safe_tenant(tenant_id)
    if not tid:
        return {"ok": False, "reason": "tenant_invalid", "writable": False}
    try:
        minutes = float(baseline_minutes_per_incident)
        mtta = float(baseline_mtta_seconds)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "baseline_invalid", "writable": False}
    if minutes < 0 or mtta < 0:
        return {"ok": False, "reason": "baseline_negative", "writable": False}
    path = _home() / "org" / "tenants" / tid / "value_baseline.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "baseline_minutes_per_incident": minutes,
        "baseline_mtta_seconds": mtta,
    }
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "writable": False,
        "baseline_source": "customer_provided",
        "tenant_id": tid,
        "path": f"org/tenants/{tid}/value_baseline.yaml",
        "baseline": payload,
        "m4_claim_allowed": False,
        "authority_note": "基线已写入租户路径。不是签收。",
    }


def get_value_baseline_view(*, role: str, tenant_id: str = "") -> Dict[str, Any]:
    if not (role or "").strip():
        return {"ok": False, "reason": "identity_missing", "writable": False}
    raw = load_value_baseline(tenant_id=tenant_id)
    return {"ok": True, "writable": False, "m4_claim_allowed": False, **raw}
