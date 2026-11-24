"""知识系统运维台（N24 residual + 产品面第一刀）。

职责：
  - 聚合统一审计 bus 近窗计数 + SLO 快照达标概况
  - 显式 residual：opt-in ``build_ops_console_snapshot`` / ``export_ops_console_snapshot``
  - 产品面第一刀：默认可用 ``build_ops_console_product_snapshot`` + schema JSON 编辑 + 浏览器导出

非目标：
  - 不宣称 N24 certified / Full unconditional / 关闭 ADR 例外
  - 不做可视化表单式 schema 设计器
  - residual 路径不可用时诚实上报 ``ops_console_unavailable`` / ``ops_console_export_unavailable``
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
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

_OPS_PRODUCT_CASES = (
    "ops_console_product_snapshot",
    "ops_console_product_schema",
    "ops_console_product_export",
    "honesty_product_certified_false",
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

    body = _collect_ops_console_metrics(
        tid,
        domain_id=domain_id,
        window_hours=window_hours,
        audit_db_path=audit_db_path,
        slo_db_path=slo_db_path,
        include_live=include_live,
    )
    return {
        **base,
        "status": "ok",
        "via": "opt_in",
        "audit": body["audit"],
        "slo": body["slo"],
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


def _collect_ops_console_metrics(
    tenant_id: str,
    *,
    domain_id: str = "",
    window_hours: int = 24,
    audit_db_path: Optional[str] = None,
    slo_db_path: Optional[str] = None,
    include_live: bool = False,
) -> Dict[str, Any]:
    """聚合审计近窗与 SLO 概况（residual / 产品面共用）。

    Args:
        tenant_id: 租户。
        domain_id: 可选域。
        window_hours: 回溯窗口小时。
        audit_db_path: 可选统一审计 bus 库。
        slo_db_path: 可选 SLO 样本库。
        include_live: SLO 是否计入 live 源。
    """
    from core.harness.knowledge_pipeline.slo_telemetry import get_slo_snapshot
    from core.harness.knowledge_pipeline.unified_audit_bus import (
        list_unified_audit_bus_events,
    )

    since = time.time() - max(1, int(window_hours)) * 3600
    audit_rows = list_unified_audit_bus_events(
        tenant_id=tenant_id,
        limit=200,
        db_path=audit_db_path,
    )
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
        tenant_id,
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


def build_ops_console_product_snapshot(
    tenant_id: str,
    *,
    domain_id: str = "",
    window_hours: int = 24,
    audit_db_path: Optional[str] = None,
    slo_db_path: Optional[str] = None,
    include_live: bool = False,
) -> Dict[str, Any]:
    """N24 产品面：运维台快照（默认可用；非 certified）。

    无 residual env 门。``full_ops_console=True`` 表示产品面四面板齐全；
    ``certified`` / ``n24_full_conformance`` 恒 false。

    Args:
        tenant_id: 租户。
        domain_id: 可选域。
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
        "full_ops_console": True,
        "product_surface": True,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}

    body = _collect_ops_console_metrics(
        tid,
        domain_id=domain_id,
        window_hours=window_hours,
        audit_db_path=audit_db_path,
        slo_db_path=slo_db_path,
        include_live=include_live,
    )
    return {
        **base,
        "status": "ok",
        "via": "product",
        "audit": body["audit"],
        "slo": body["slo"],
        "panels": {
            "unified_audit": True,
            "slo_telemetry": True,
            "export_download": True,
            "schema_editor": True,
        },
        "note": (
            "ops console product surface (slice-1); "
            "not N24 certified / Full remains conditional"
        ),
    }


def get_ops_console_schema(
    *,
    tenant_id: str,
    object_type_id: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N24 产品面：读取 ObjectType schema（最新版本优先，否则列表）。

    Args:
        tenant_id: 租户。
        object_type_id: 可选类型过滤；空则返回租户下近期版本列表。
        db_path: 可选 ObjectType 发布库。
    """
    from core.harness.knowledge_pipeline.object_type_publish import (
        list_object_type_versions,
    )

    tid = str(tenant_id or "").strip()
    oid = str(object_type_id or "").strip()
    base = {
        "tenant_id": tid,
        "object_type_id": oid,
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": True,
        "schema_editor": True,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}

    items = list_object_type_versions(
        tenant_id=tid,
        object_type_id=oid,
        limit=50,
        db_path=db_path,
    )
    current: Optional[Dict[str, Any]] = None
    if oid:
        # 为什么：优先 published，否则取最近一条供编辑器回填
        published = [i for i in items if i.get("status") == "published"]
        current = published[-1] if published else (items[-1] if items else None)
    return {
        **base,
        "status": "ok",
        "via": "product",
        "items": items,
        "current": current,
        "definition": (current or {}).get("definition")
        if isinstance(current, dict)
        else None,
        "note": "ops console schema editor product surface; not certified",
    }


def save_ops_console_schema(
    *,
    tenant_id: str,
    object_type_id: str,
    definition: Dict[str, Any],
    actor: str = "ops-console-product",
    reason: str = "ops console schema editor save",
    version: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N24 产品面：保存 ObjectType schema 为 draft（复用发布面，非第二存贮）。

    Args:
        tenant_id: 租户。
        object_type_id: 类型 id。
        definition: 类型定义 JSON。
        actor: 提交人。
        reason: 理由。
        version: 可选版本；缺省自动生成。
        db_path: 可选 ObjectType 发布库。
    """
    from core.harness.knowledge_pipeline.object_type_publish import (
        ObjectTypePublishError,
        submit_object_type_draft,
    )

    tid = str(tenant_id or "").strip()
    oid = str(object_type_id or "").strip()
    base = {
        "tenant_id": tid,
        "object_type_id": oid,
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": True,
        "schema_editor": True,
    }
    if not tid or not oid:
        return {**base, "status": "invalid", "error": "tenant_object_type_required"}
    if not isinstance(definition, dict) or not definition:
        return {**base, "status": "invalid", "error": "definition_required"}

    ver = str(version or "").strip() or f"ops-{uuid.uuid4().hex[:10]}"
    try:
        out = submit_object_type_draft(
            tenant_id=tid,
            object_type_id=oid,
            version=ver,
            definition=definition,
            actor=str(actor or "ops-console-product").strip() or "ops-console-product",
            reason=str(reason or "ops console schema editor save").strip()
            or "ops console schema editor save",
            db_path=db_path,
        )
    except ObjectTypePublishError as exc:
        return {**base, "status": "invalid", "error": str(exc), "version": ver}

    return {
        **base,
        "status": "ok",
        "via": "product",
        "draft": out,
        "version": ver,
        "note": "schema saved as draft via object_type_publish; not certified",
    }


def export_ops_console_product(
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
    """N24 产品面：浏览器可下载 JSON 导出（无 EXPORT env 门；非 certified）。

    Args:
        tenant_id: 租户。
        domain_id: 可选域。
        window_hours: 回溯窗口小时。
        audit_db_path: 可选统一审计 bus 库。
        slo_db_path: 可选 SLO 样本库。
        include_live: SLO 是否计入 live 源。
        output_root: 可选写盘根（须 allowlist）。
        write: 是否顺带服务端写盘。
    """
    tid = str(tenant_id or "").strip()
    base: Dict[str, Any] = {
        "tenant_id": tid,
        "domain_id": str(domain_id or ""),
        "window_hours": int(window_hours),
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": True,
        "export_complete": False,
        "product_surface": True,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}

    snap = build_ops_console_product_snapshot(
        tid,
        domain_id=domain_id,
        window_hours=window_hours,
        audit_db_path=audit_db_path,
        slo_db_path=slo_db_path,
        include_live=include_live,
    )
    if snap.get("status") != "ok":
        return {
            **base,
            "status": "invalid",
            "error": f"snapshot_not_ok:{snap.get('status')}",
            "snapshot": snap,
        }

    payload = {
        "kind": "ops_console_product_export",
        "tenant_id": tid,
        "domain_id": str(domain_id or ""),
        "window_hours": int(window_hours),
        "exported_at": time.time(),
        "certified": False,
        "full_ops_console": True,
        "export_complete": False,
        "snapshot": {
            "status": snap.get("status"),
            "audit": snap.get("audit"),
            "slo": snap.get("slo"),
            "panels": snap.get("panels"),
        },
        "download_filename": f"{tid}-ops-console-product.json",
    }
    out_path = ""
    if write:
        root_info = resolve_ops_console_export_root(output_root=output_root)
        if not root_info.get("ok"):
            return {
                **base,
                "status": "denied",
                "via": "product",
                "reason": root_info.get("reason") or "output_root_denied",
                "allowlist": root_info.get("allowlist"),
                "payload": payload,
            }
        root = Path(str(root_info["output_root"]))
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{tid}-ops-console-product.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        out_path = str(target)

    return {
        **base,
        "status": "ok",
        "via": "product",
        "output_path": out_path or None,
        "wrote": bool(out_path),
        "payload": payload,
        "panels": {
            "unified_audit": True,
            "slo_telemetry": True,
            "export_download": True,
            "schema_editor": True,
        },
        "note": (
            "ops console product export; browser download ready; "
            "export_complete remains false / not N24 certified"
        ),
    }


def run_ops_console_product_suite(
    *,
    tenant_id: str = "n24-ops-console-product-tenant",
) -> Dict[str, Any]:
    """N24 产品面套件：默认可用 + schema + 导出；certified 恒 false。

    Args:
        tenant_id: 套件租户。
    """
    from core.harness.knowledge_pipeline.slo_telemetry import record_slo_sample
    from core.harness.knowledge_pipeline.unified_audit_bus import (
        append_unified_audit_event,
    )

    cases: List[Dict[str, Any]] = []
    prev_home = os.environ.get("AIPLAT_HOME")
    tmp = tempfile.TemporaryDirectory(prefix="n24-ops-console-product-")
    try:
        root = Path(tmp.name)
        os.environ["AIPLAT_HOME"] = str(root / "home")
        audit_db = str(root / "audit.sqlite3")
        slo_db = str(root / "slo.sqlite3")
        ot_db = str(root / "object_types.sqlite3")

        now = time.time()
        append_unified_audit_event(
            tenant_id=tenant_id,
            event_id=f"ops-console-product-probe-{tenant_id}",
            stream="ops_console_product_probe",
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
            35.0,
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

        # 为什么：产品面无 env 门——显式清掉 residual 开关仍应可用
        prev_shell = os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE", None)
        prev_export = os.environ.pop("AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT", None)
        try:
            snap = build_ops_console_product_snapshot(
                tenant_id,
                audit_db_path=audit_db,
                slo_db_path=slo_db,
                include_live=False,
            )
            panels = snap.get("panels") or {}
            cases.append(
                {
                    "id": "ops_console_product_snapshot",
                    "ok": snap.get("status") == "ok"
                    and snap.get("full_ops_console") is True
                    and snap.get("certified") is False
                    and panels.get("schema_editor") is True
                    and panels.get("export_download") is True
                    and int((snap.get("audit") or {}).get("recent_count") or 0) >= 1,
                }
            )

            saved = save_ops_console_schema(
                tenant_id=tenant_id,
                object_type_id="OpsProbeType",
                definition={
                    "object_type_id": "OpsProbeType",
                    "label": "ops probe",
                    "fields": [],
                },
                actor="suite",
                reason="product suite schema",
                db_path=ot_db,
            )
            loaded = get_ops_console_schema(
                tenant_id=tenant_id,
                object_type_id="OpsProbeType",
                db_path=ot_db,
            )
            cases.append(
                {
                    "id": "ops_console_product_schema",
                    "ok": saved.get("status") == "ok"
                    and loaded.get("status") == "ok"
                    and isinstance(loaded.get("definition"), dict)
                    and loaded.get("schema_editor") is True,
                }
            )

            exported = export_ops_console_product(
                tenant_id,
                audit_db_path=audit_db,
                slo_db_path=slo_db,
                include_live=False,
                write=True,
            )
            payload = exported.get("payload") or {}
            cases.append(
                {
                    "id": "ops_console_product_export",
                    "ok": exported.get("status") == "ok"
                    and exported.get("full_ops_console") is True
                    and exported.get("export_complete") is False
                    and bool(payload.get("download_filename"))
                    and bool(exported.get("wrote")),
                }
            )
            cases.append(
                {
                    "id": "honesty_product_certified_false",
                    "ok": snap.get("certified") is False
                    and snap.get("n24_full_conformance") is False
                    and snap.get("n24_unified_audit_freeze") is True
                    and exported.get("certified") is False,
                }
            )
        finally:
            if prev_shell is not None:
                os.environ["AIPLAT_KNOWLEDGE_OPS_CONSOLE"] = prev_shell
            if prev_export is not None:
                os.environ["AIPLAT_KNOWLEDGE_OPS_CONSOLE_EXPORT"] = prev_export
    finally:
        if prev_home is None:
            os.environ.pop("AIPLAT_HOME", None)
        else:
            os.environ["AIPLAT_HOME"] = prev_home
        tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_OPS_PRODUCT_CASES)
        and len(cases) == len(_OPS_PRODUCT_CASES),
        "passed": passed,
        "total": len(_OPS_PRODUCT_CASES),
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": True,
        "export_complete": False,
        "product_surface": True,
        "note": (
            "Ops console product surface suite; full_ops_console true; "
            "not N24 certified"
        ),
    }


def evaluate_ops_console_product_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 产品面门槛门：要求 full_ops_console；禁止 certified。

    Args:
        suite: ``run_ops_console_product_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_ops_console_product_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("full_ops_console") is not True:
        issues.append("product_full_ops_console_required")
    if s.get("export_complete") is True:
        issues.append("honesty_export_complete_forbidden")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _OPS_PRODUCT_CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "n24_unified_audit_freeze": True,
        "full_ops_console": True,
        "export_complete": False,
        "product_surface": True,
        "note": "Ops console product gate; not N24 certified",
    }
