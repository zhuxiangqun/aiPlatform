"""知识系统运维台薄壳（N24 residual）。

职责：
  - 聚合统一审计 bus 近窗计数 + SLO 快照达标概况
  - 显式 residual：opt-in ``build_ops_console_snapshot``
  - 显式 residual：opt-in ``export_ops_console_snapshot``（有界 JSON 写盘）

非目标：
  - 不做全量运维台 / JSON schema 编辑器 / 通用下载产品化
  - 不宣称 N24 certified / Full unconditional
  - 不可用时诚实上报 ``ops_console_unavailable`` / ``ops_console_export_unavailable``
"""
from __future__ import annotations

import json
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

_OPS_EXPORT_CASES = (
    "ops_console_export_unavailable",
    "ops_console_export_opt_in",
    "honesty_export_certified_false",
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
            # 为什么：导出是另一把 opt-in residual；壳快照不暗示下载产品化已开
            "export_download": False,
            "schema_editor": False,
        },
        "note": (
            "ops console shell residual only; not full ops console / "
            "not N24 certified / Full remains conditional"
        ),
    }


def resolve_ops_console_export_root(
    *,
    output_root: Optional[str] = None,
) -> Dict[str, Any]:
    """解析运维台导出写盘根（仅允许 ``AIPLAT_HOME/data/knowledge_ops_console_export``）。

    Args:
        output_root: 可选显式根；须落在 allowlist 下。
    """
    home = (os.environ.get("AIPLAT_HOME") or "").strip()
    if not home:
        home = str(Path.cwd() / ".aiplat-home")
    allow = (
        Path(home).resolve() / "data" / "knowledge_ops_console_export"
    ).resolve()
    if output_root:
        cand = Path(output_root).resolve()
        try:
            cand.relative_to(allow)
        except ValueError:
            return {
                "ok": False,
                "reason": "output_root_not_allowlisted",
                "allowlist": str(allow),
                "output_root": str(cand),
            }
        return {"ok": True, "output_root": str(cand), "allowlist": str(allow)}
    return {"ok": True, "output_root": str(allow), "allowlist": str(allow)}


def export_ops_console_snapshot(
    tenant_id: str,
    *,
    domain_id: str = "",
    window_hours: int = 24,
    audit_db_path: Optional[str] = None,
    slo_db_path: Optional[str] = None,
    include_live: bool = False,
    output_root: Optional[str] = None,
    write: bool = False,
) -> Dict[str, Any]:
    """N24 residual：有界运维台快照 JSON 导出（非全量下载产品化 / 非 certified）。

    默认关闭（无 ``AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT=1`` →
    ``ops_console_export_unavailable``）。写盘仅落 allowlist。
    ``certified`` / ``full_ops_console`` 恒 false；``schema_editor`` 恒 false。

    Args:
        tenant_id: 租户。
        domain_id: 可选域。
        window_hours: 回溯窗口小时。
        audit_db_path: 可选统一审计 bus 库。
        slo_db_path: 可选 SLO 样本库。
        include_live: SLO 是否计入 live 源。
        output_root: 可选写盘根（须 allowlist）。
        write: 是否写盘。
    """
    tid = str(tenant_id or "").strip()
    base: Dict[str, Any] = {
        "tenant_id": tid,
        "domain_id": str(domain_id or ""),
        "window_hours": int(window_hours),
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": False,
        "export_complete": False,
        "schema_editor": False,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}

    # 为什么：默认关闭导出，避免把壳快照误当通用下载/运维台产品化
    if os.environ.get(
        "AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT", ""
    ).strip().lower() not in {"1", "true", "yes"}:
        return {
            **base,
            "status": "ops_console_export_unavailable",
            "via": "env_disabled",
            "note": (
                "set AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT=1 "
                "to enable bounded ops console export"
            ),
        }

    prev_shell = os.environ.get("AIPLAT_KNOWLEDGE_OPS_CONSOLE")
    # 为什么：导出复用壳快照聚合；临时打开壳开关，不永久改动调用方环境
    os.environ["AIPLAT_KNOWLEDGE_OPS_CONSOLE"] = "1"
    try:
        snap = build_ops_console_snapshot(
            tid,
            domain_id=domain_id,
            window_hours=window_hours,
            audit_db_path=audit_db_path,
            slo_db_path=slo_db_path,
            include_live=include_live,
        )
    finally:
        if prev_shell is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_OPS_CONSOLE"] = prev_shell

    if snap.get("status") != "ok":
        return {
            **base,
            "status": "invalid",
            "error": f"snapshot_not_ok:{snap.get('status')}",
            "snapshot": snap,
        }

    payload = {
        "kind": "ops_console_export_residual",
        "tenant_id": tid,
        "domain_id": str(domain_id or ""),
        "window_hours": int(window_hours),
        "exported_at": time.time(),
        "certified": False,
        "full_ops_console": False,
        "export_complete": False,
        "snapshot": {
            "status": snap.get("status"),
            "audit": snap.get("audit"),
            "slo": snap.get("slo"),
            "panels": {
                **dict(snap.get("panels") or {}),
                "export_download": True,
                "schema_editor": False,
            },
        },
    }
    out_path = ""
    if write:
        root_info = resolve_ops_console_export_root(output_root=output_root)
        if not root_info.get("ok"):
            return {
                **base,
                "status": "denied",
                "via": "opt_in",
                "reason": root_info.get("reason") or "output_root_denied",
                "allowlist": root_info.get("allowlist"),
                "payload": payload,
            }
        root = Path(str(root_info["output_root"]))
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{tid}-ops-console-export.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        out_path = str(target)

    return {
        **base,
        "status": "ok",
        "via": "opt_in",
        "output_path": out_path or None,
        "wrote": bool(out_path),
        "payload": payload,
        "panels": {
            "unified_audit": True,
            "slo_telemetry": True,
            "export_download": True,
            "schema_editor": False,
        },
        "note": (
            "ops console export residual only; not full download product / "
            "not full ops console / not N24 certified"
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


def run_ops_console_export_suite(
    *,
    tenant_id: str = "n24-ops-console-export-tenant",
) -> Dict[str, Any]:
    """N24 residual：运维台导出套件（certified / full 恒 false）。

    Args:
        tenant_id: 套件租户。
    """
    from core.harness.knowledge_pipeline.slo_telemetry import record_slo_sample
    from core.harness.knowledge_pipeline.unified_audit_bus import (
        append_unified_audit_event,
    )

    cases: List[Dict[str, Any]] = []
    prev_export = os.environ.get("AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT")
    prev_home = os.environ.get("AIPLAT_HOME")
    os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT", None)
    tmp = tempfile.TemporaryDirectory(prefix="n24-ops-console-export-")
    try:
        root = Path(tmp.name)
        os.environ["AIPLAT_HOME"] = str(root / "home")
        audit_db = str(root / "audit.sqlite3")
        slo_db = str(root / "slo.sqlite3")

        unavail = export_ops_console_snapshot(
            tenant_id,
            audit_db_path=audit_db,
            slo_db_path=slo_db,
            include_live=False,
            write=False,
        )
        cases.append(
            {
                "id": "ops_console_export_unavailable",
                "ok": unavail.get("status") == "ops_console_export_unavailable"
                and unavail.get("certified") is False
                and unavail.get("full_ops_console") is False
                and unavail.get("export_complete") is False,
            }
        )

        now = time.time()
        append_unified_audit_event(
            tenant_id=tenant_id,
            event_id=f"ops-console-export-probe-{tenant_id}",
            stream="ops_console_export_probe",
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
            40.0,
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

        os.environ["AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT"] = "1"
        exported = export_ops_console_snapshot(
            tenant_id,
            audit_db_path=audit_db,
            slo_db_path=slo_db,
            include_live=False,
            write=True,
        )
        out_path = str(exported.get("output_path") or "")
        wrote_ok = bool(out_path) and Path(out_path).is_file()
        panels = exported.get("panels") or {}
        cases.append(
            {
                "id": "ops_console_export_opt_in",
                "ok": exported.get("status") == "ok"
                and wrote_ok
                and panels.get("export_download") is True
                and panels.get("schema_editor") is False
                and exported.get("certified") is False
                and exported.get("full_ops_console") is False
                and exported.get("export_complete") is False,
            }
        )
        cases.append(
            {
                "id": "honesty_export_certified_false",
                "ok": exported.get("certified") is False
                and exported.get("n24_unified_audit_freeze") is True
                and exported.get("schema_editor") is False,
            }
        )
    finally:
        if prev_export is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT"] = prev_export
        if prev_home is None:
            os.environ.pop("AIPLAT_HOME", None)
        else:
            os.environ["AIPLAT_HOME"] = prev_home
        tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_OPS_EXPORT_CASES)
        and len(cases) == len(_OPS_EXPORT_CASES),
        "passed": passed,
        "total": len(_OPS_EXPORT_CASES),
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": False,
        "export_complete": False,
        "note": (
            "Ops console export residual; not full download product / "
            "not full ops console / not N24 certified"
        ),
    }


def evaluate_ops_console_export_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 residual：运维台导出门槛门；certified / full 恒 false。

    Args:
        suite: ``run_ops_console_export_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_ops_console_export_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("full_ops_console") is True:
        issues.append("honesty_full_ops_console_forbidden")
    if s.get("export_complete") is True:
        issues.append("honesty_export_complete_forbidden")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _OPS_EXPORT_CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": False,
        "export_complete": False,
        "note": "Ops console export residual gate; not N24 certified",
    }
