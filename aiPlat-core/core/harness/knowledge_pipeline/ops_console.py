"""知识系统运维台薄壳（N24 residual）。

职责：
  - 聚合统一审计 bus 近窗计数 + SLO 快照达标概况
  - 显式 residual：opt-in ``build_ops_console_snapshot``

非目标：
  - 不做全量运维台 / JSON schema 编辑器 / 导出下载产品化
  - 不宣称 N24 certified / Full unconditional
  - 不可用时诚实上报 ``ops_console_unavailable``
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_OPS_CASES = (
    "ops_console_unavailable",
    "ops_console_opt_in",
    "honesty_certified_false",
)


def build_ops_console_snapshot(
    tenant_id: str,
    *,
    domain_id: str = "",
    window_hours: int = 24,
    audit_db_path: Optional[str] = None,
    slo_db_path: Optional[str] = None,
    include_live: bool = False,
) -> Dict[str, Any]:
    """N24 residual：运维台薄壳快照（非全量 ops console / 非 certified）。

    默认关闭（无 ``AIPLAT_KNOWLEDGE_OPS_CONSOLE=1`` → ``ops_console_unavailable``）。

    Args:
        tenant_id: 租户。
        domain_id: 可选域（透传 SLO）。
        window_hours: 回溯窗口小时。
        audit_db_path: 可选统一审计 bus 库。
        slo_db_path: 可选 SLO 样本库。
        include_live: SLO 是否计入 live 源。
    """
    tid = str(tenant_id or "").strip()
    base = {
        "tenant_id": tid,
        "domain_id": str(domain_id or ""),
        "window_hours": int(window_hours),
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": False,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}

    # 为什么：默认关闭运维台聚合，避免把统一审计 UI 误当全量 ops console
    if os.environ.get("AIPLAT_KNOWLEDGE_OPS_CONSOLE", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return {
            **base,
            "status": "ops_console_unavailable",
            "via": "env_disabled",
            "note": "set AIPLAT_KNOWLEDGE_OPS_CONSOLE=1 to enable ops console shell",
        }

    from core.harness.knowledge_pipeline.slo_telemetry import get_slo_snapshot
    from core.harness.knowledge_pipeline.unified_audit_bus import (
        list_unified_audit_bus_events,
    )

    since = time.time() - max(1, int(window_hours)) * 3600
    audit_rows = list_unified_audit_bus_events(
        tenant_id=tid,
        limit=200,
        db_path=audit_db_path,
    )
    # list returns dict with items or a list depending on API — normalize
    if isinstance(audit_rows, dict):
        items = list(audit_rows.get("items") or audit_rows.get("events") or [])
    else:
        items = list(audit_rows or [])
    recent_audit = []
    for r in items:
        if not isinstance(r, dict):
            continue
        # 为什么：occurred_at=0 的幂等探针仍用 recorded_at 进近窗，避免假空台
        ts = float(r.get("occurred_at") or 0)
        if ts <= 0:
            ts = float(r.get("recorded_at") or r.get("created_at") or 0)
        if ts >= since:
            recent_audit.append(r)

    snap = get_slo_snapshot(
        tid,
        domain_id=domain_id,
        window_hours=window_hours,
        db_path=slo_db_path,
        include_live=include_live,
    )
    metrics = (snap.get("metrics") or {}) if isinstance(snap, dict) else {}
    miss = [
        mid
        for mid, m in metrics.items()
        if isinstance(m, dict) and m.get("meets_target") is not True
    ]

    return {
        **base,
        "status": "ok",
        "via": "opt_in",
        "audit": {
            "recent_count": len(recent_audit),
            "listed": len(items),
            "window_hours": int(window_hours),
        },
        "slo": {
            "snapshot_status": snap.get("status") if isinstance(snap, dict) else "error",
            "miss_metrics": miss,
            "miss_count": len(miss),
        },
        "panels": {
            "unified_audit": True,
            "slo_telemetry": True,
            "export_download": False,
            "schema_editor": False,
        },
        "note": (
            "ops console shell residual only; not full ops console / "
            "not N24 certified / Full remains conditional"
        ),
    }


def run_ops_console_suite(
    *,
    tenant_id: str = "n24-ops-console-tenant",
) -> Dict[str, Any]:
    """N24 residual：运维台薄壳套件（certified 恒 false）。

    Args:
        tenant_id: 套件租户。
    """
    from core.harness.knowledge_pipeline.slo_telemetry import record_slo_sample
    from core.harness.knowledge_pipeline.unified_audit_bus import (
        append_unified_audit_event,
    )

    cases: List[Dict[str, Any]] = []
    prev = os.environ.get("AIPLAT_KNOWLEDGE_OPS_CONSOLE")
    os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE", None)
    tmp = tempfile.TemporaryDirectory(prefix="n24-ops-console-")
    try:
        root = Path(tmp.name)
        audit_db = str(root / "audit.sqlite3")
        slo_db = str(root / "slo.sqlite3")

        unavail = build_ops_console_snapshot(
            tenant_id,
            audit_db_path=audit_db,
            slo_db_path=slo_db,
            include_live=False,
        )
        cases.append(
            {
                "id": "ops_console_unavailable",
                "ok": unavail.get("status") == "ops_console_unavailable"
                and unavail.get("certified") is False
                and unavail.get("full_ops_console") is False,
            }
        )

        now = time.time()
        append_unified_audit_event(
            tenant_id=tenant_id,
            event_id=f"ops-console-probe-{tenant_id}",
            stream="ops_console_probe",
            event_type="probe",
            occurred_at=now,
            payload={"ok": True},
            db_path=audit_db,
        )
        record_slo_sample(
            "action_success_rate",
            1.0,
            tenant_id=tenant_id,
            ok=True,
            db_path=slo_db,
        )
        record_slo_sample(
            "query_p95_ms",
            50.0,
            tenant_id=tenant_id,
            ok=True,
            db_path=slo_db,
        )
        record_slo_sample(
            "citation_coverage",
            1.0,
            tenant_id=tenant_id,
            ok=True,
            db_path=slo_db,
        )

        os.environ["AIPLAT_KNOWLEDGE_OPS_CONSOLE"] = "1"
        snap = build_ops_console_snapshot(
            tenant_id,
            audit_db_path=audit_db,
            slo_db_path=slo_db,
            include_live=False,
        )
        cases.append(
            {
                "id": "ops_console_opt_in",
                "ok": snap.get("status") == "ok"
                and int((snap.get("audit") or {}).get("recent_count") or 0) >= 1
                and snap.get("certified") is False
                and snap.get("n24_full_conformance") is False
                and snap.get("full_ops_console") is False,
            }
        )
        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": snap.get("certified") is False
                and snap.get("n24_unified_audit_freeze") is True,
            }
        )
    finally:
        if prev is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_OPS_CONSOLE"] = prev
        tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_OPS_CASES) and len(cases) == len(_OPS_CASES),
        "passed": passed,
        "total": len(_OPS_CASES),
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": False,
        "note": "Ops console shell residual; not full ops console / not N24 certified",
    }


def evaluate_ops_console_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 residual：运维台薄壳门槛门；certified 恒 false。

    Args:
        suite: ``run_ops_console_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_ops_console_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("full_ops_console") is True:
        issues.append("honesty_full_ops_console_forbidden")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _OPS_CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": False,
        "note": "Ops console shell residual gate; not N24 certified",
    }
