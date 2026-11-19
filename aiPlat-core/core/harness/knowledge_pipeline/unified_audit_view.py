"""N24 Unified Audit View（Batch J3/J5/J7）— Package + Action + revision + bus + ActionStore。

职责：按租户 fan-in 多源审计为统一列表；suite/gate 诚实锁。
非目标：不宣称 N24 certified；不改写 ActionStore 历史。
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_DEFAULT_STREAMS = (
    "package",
    "action_execution",
    "revision_audit",
    "action_store",
    "bus",
)
_N24_UNIFIED_AUDIT_CASES = (
    "package_stream_present",
    "action_stream_present",
    "revision_stream_present",
    "action_store_stream_present",
    "cross_tenant_empty",
)


def _resolve_streams(streams: Optional[Sequence[str]]) -> List[str]:
    """解析流集合（参数 > 环境变量 > 默认五流含 action_store/bus）。

    Args:
        streams: 显式流名；空则读 env / 默认。
    """
    if streams:
        out = [str(s).strip() for s in streams if str(s).strip()]
        return out or list(_DEFAULT_STREAMS)
    env = (os.environ.get("AIPLAT_UNIFIED_AUDIT_STREAMS") or "").strip()
    if env:
        return [p.strip() for p in env.split(",") if p.strip()]
    return list(_DEFAULT_STREAMS)


def _norm_ts(value: Any) -> float:
    """归一化时间戳为 float（不可解析 → 0）。

    Args:
        value: 原始时间字段。
    """
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _package_events(
    *,
    tenant_id: str,
    package_id: str,
    limit: int,
    db_path: Optional[str],
) -> List[Dict[str, Any]]:
    """Package 版本行 → 统一事件。

    Args:
        tenant_id: 租户。
        package_id: 可选包过滤。
        limit: 上限。
        db_path: Package DB。
    """
    from core.harness.knowledge_pipeline.ontology_package import list_package_versions

    rows = list_package_versions(
        tenant_id=tenant_id,
        package_id=package_id,
        limit=limit,
        db_path=db_path,
    )
    events: List[Dict[str, Any]] = []
    for row in rows:
        status = str(row.get("status") or "published")
        occurred = row.get("rolled_back_at") if status == "rolled_back" else row.get("published_at")
        events.append(
            {
                "stream": "package",
                "tenant_id": tenant_id,
                "event_id": f"pkg:{row.get('package_id')}:{row.get('version')}",
                "event_type": status,
                "occurred_at": _norm_ts(occurred),
                "actor": "",
                "subject": f"{row.get('package_id')}@{row.get('version')}",
                "refs": {"content_hash": row.get("content_hash") or ""},
                "payload": row,
            }
        )
    return events


def _action_events(
    *,
    tenant_id: str,
    action_id_prefix: str,
    limit: int,
    db_path: Optional[str],
) -> List[Dict[str, Any]]:
    """ActionExecution 行 → 统一事件。

    Args:
        tenant_id: 租户。
        action_id_prefix: 可选前缀。
        limit: 上限。
        db_path: ActionExecution DB。
    """
    from core.harness.infrastructure.action_execution import list_action_executions

    rows = list_action_executions(
        tenant_id=tenant_id,
        action_id_prefix=action_id_prefix,
        limit=limit,
        db_path=db_path,
    )
    events: List[Dict[str, Any]] = []
    for row in rows:
        occurred = row.get("completed_at") or row.get("started_at")
        events.append(
            {
                "stream": "action_execution",
                "tenant_id": tenant_id,
                "event_id": str(row.get("execution_id") or ""),
                "event_type": str(row.get("status") or "executed"),
                "occurred_at": _norm_ts(occurred),
                "actor": str(row.get("actor") or ""),
                "subject": str(row.get("action_id") or ""),
                "refs": {
                    "idempotency_key": row.get("idempotency_key") or "",
                    "audit_hash": row.get("audit_hash") or "",
                },
                "payload": row,
            }
        )
    return events


async def _revision_events(
    *,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    limit: int,
    fact_ledger: Any,
) -> List[Dict[str, Any]]:
    """revision_audit 行 → 统一事件。

    Args:
        tenant_id: 租户。
        entity_type: 可选实体类型。
        entity_id: 可选实体 ID。
        limit: 上限。
        fact_ledger: FactLedger 实例。
    """
    rows = await fact_ledger.list_revision_audit(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )
    events: List[Dict[str, Any]] = []
    for row in rows:
        et = str(row.get("entity_type") or "")
        eid = str(row.get("entity_id") or "")
        events.append(
            {
                "stream": "revision_audit",
                "tenant_id": tenant_id,
                "event_id": str(row.get("audit_id") or ""),
                "event_type": str(row.get("event_type") or ""),
                "occurred_at": _norm_ts(row.get("recorded_at")),
                "actor": str(row.get("actor") or ""),
                "subject": f"{et}:{eid}" if et or eid else "",
                "refs": {
                    "revision": row.get("revision"),
                    "reason": row.get("reason") or "",
                },
                "payload": row,
            }
        )
    return events


def _bus_events(
    *,
    tenant_id: str,
    limit: int,
    db_path: Optional[str],
) -> List[Dict[str, Any]]:
    """总线表行 → 统一事件（stream 标记为 bus）。

    Args:
        tenant_id: 租户。
        limit: 上限。
        db_path: 总线 DB。
    """
    from core.harness.knowledge_pipeline.unified_audit_bus import (
        list_unified_audit_bus_events,
    )

    rows = list_unified_audit_bus_events(
        tenant_id=tenant_id, limit=limit, db_path=db_path
    )
    events: List[Dict[str, Any]] = []
    for row in rows:
        refs = dict(row.get("refs") or {})
        refs["source_stream"] = row.get("stream") or ""
        events.append(
            {
                "stream": "bus",
                "tenant_id": tenant_id,
                "event_id": str(row.get("event_id") or ""),
                "event_type": str(row.get("event_type") or ""),
                "occurred_at": _norm_ts(row.get("occurred_at")),
                "actor": str(row.get("actor") or ""),
                "subject": str(row.get("subject") or ""),
                "refs": refs,
                "payload": row.get("payload") or {},
            }
        )
    return events


def _parse_created_at(value: Any) -> float:
    """解析 ActionStore created_at（RFC3339 / sqlite datetime / epoch）。

    Args:
        value: 原始时间字段。
    """
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        # 为什么：非数字时间串继续走 ISO 解析，不静默吞掉
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return 0.0


async def _action_store_events(
    *,
    tenant_id: str,
    domain_id: str,
    limit: int,
    db_path: Optional[str],
) -> List[Dict[str, Any]]:
    """ActionStore.action_audit → 统一事件（物理 tenant_id 优先过滤）。

    Args:
        tenant_id: 租户。
        domain_id: 可选域过滤。
        limit: 上限。
        db_path: ActionStore DB。
    """
    from core.harness.infrastructure.action_store import ActionStore

    store = ActionStore(db_path) if db_path else ActionStore()
    await store.initialize()
    rows = await store.list_audit(
        entity_id="",
        domain_id=(domain_id or "").strip(),
        tenant_id=tenant_id,
        limit=limit,
    )
    events: List[Dict[str, Any]] = []
    for row in rows:
        events.append(
            {
                "stream": "action_store",
                "tenant_id": tenant_id,
                "event_id": str(row.get("audit_id") or ""),
                "event_type": str(row.get("result_status") or "executed"),
                "occurred_at": _parse_created_at(row.get("created_at")),
                "actor": str(row.get("actor") or ""),
                "subject": str(row.get("action_id") or ""),
                "refs": {
                    "entity_id": row.get("entity_id") or "",
                    "domain_id": row.get("domain_id") or "",
                },
                "payload": row,
            }
        )
    return events


async def list_unified_audit_events(
    *,
    tenant_id: str,
    streams: Optional[Sequence[str]] = None,
    package_id: str = "",
    action_id_prefix: str = "",
    entity_type: str = "",
    entity_id: str = "",
    domain_id: str = "",
    limit: int = 100,
    package_db_path: Optional[str] = None,
    action_execution_db_path: Optional[str] = None,
    action_store_db_path: Optional[str] = None,
    bus_db_path: Optional[str] = None,
    fact_ledger: Any = None,
) -> Dict[str, Any]:
    """汇合 Package / ActionExecution / revision_audit / ActionStore / bus。

    Args:
        tenant_id: 租户（必填）。
        streams: 可选流过滤；默认五流或 ``AIPLAT_UNIFIED_AUDIT_STREAMS``。
        package_id: Package 流可选过滤。
        action_id_prefix: Action 流可选前缀。
        entity_type: revision 流可选实体类型。
        entity_id: revision 流可选实体 ID。
        domain_id: ActionStore 流可选域过滤。
        limit: 汇合后最大条数（1–500）。
        package_db_path: 可选 Package DB。
        action_execution_db_path: 可选 ActionExecution DB。
        action_store_db_path: 可选 ActionStore DB。
        bus_db_path: 可选统一审计总线 DB。
        fact_ledger: 可选 FactLedger；默认单例。

    Returns:
        ``{events, streams, certified:false, ...}``。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id required")
    lim = max(1, min(int(limit or 100), 500))
    active = _resolve_streams(streams)
    # 每流多取一些再截断，避免单流挤占
    per = max(lim, lim)

    events: List[Dict[str, Any]] = []
    if "package" in active:
        events.extend(
            _package_events(
                tenant_id=tid,
                package_id=package_id,
                limit=per,
                db_path=package_db_path,
            )
        )
    if "action_execution" in active:
        ae_path = action_execution_db_path
        if ae_path is None and fact_ledger is not None:
            ae_path = getattr(fact_ledger, "action_execution_db_path", None)
        events.extend(
            _action_events(
                tenant_id=tid,
                action_id_prefix=action_id_prefix,
                limit=per,
                db_path=ae_path,
            )
        )
    if "revision_audit" in active:
        from core.harness.knowledge_pipeline.fact_ledger import get_fact_ledger

        lg = fact_ledger if fact_ledger is not None else get_fact_ledger()
        await lg.initialize()
        events.extend(
            await _revision_events(
                tenant_id=tid,
                entity_type=entity_type,
                entity_id=entity_id,
                limit=per,
                fact_ledger=lg,
            )
        )
    if "action_store" in active:
        events.extend(
            await _action_store_events(
                tenant_id=tid,
                domain_id=domain_id,
                limit=per,
                db_path=action_store_db_path,
            )
        )
    if "bus" in active:
        events.extend(
            _bus_events(tenant_id=tid, limit=per, db_path=bus_db_path)
        )

    events.sort(key=lambda e: (_norm_ts(e.get("occurred_at")), str(e.get("event_id") or "")))
    clipped = events[:lim]
    return {
        "events": clipped,
        "count": len(clipped),
        "streams": active,
        "tenant_id": tid,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Package+Action+revision+ActionStore+bus merge; not N24 certified",
    }


async def run_unified_audit_view_suite(
    *,
    tenant_id: str = "n24-unified-audit-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 统一审计视图最小套件（certified 恒 false）。

    Args:
        tenant_id: 写入租户。
        domain_id: 可选域（透传 FactLedger）。

    Returns:
        套件汇总。
    """
    from core.harness.infrastructure.action_execution import persist_execution
    from core.harness.infrastructure.action_store import ActionStore
    from core.harness.knowledge_pipeline.fact_ledger import FactLedger
    from core.harness.knowledge_pipeline.ontology_package import publish_package

    tmp = tempfile.TemporaryDirectory(prefix="n24-unified-audit-")
    cases: List[Dict[str, Any]] = []
    try:
        root = Path(tmp.name)
        pkg_db = str(root / "ontology_package.sqlite3")
        act_db = str(root / "action_execution.sqlite3")
        store_db = str(root / "action_store.sqlite3")
        bus_db = str(root / "unified_audit_bus.sqlite3")
        os.environ["AIPLAT_UNIFIED_AUDIT_BUS_DB"] = bus_db
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
            action_execution_db_path=act_db,
        )
        await lg.initialize()

        pub = publish_package(
            tenant_id=tenant_id,
            package_id="n24-pkg",
            version="1.0.0",
            schema=["InstallOrder"],
            db_path=pkg_db,
        )
        persist_execution(
            {
                "tenant_id": tenant_id,
                "idempotency_key": "n24-unified-act-1",
                "action_id": "knowledge_revision:suite_probe",
                "actor": "suite",
                "status": "succeeded",
                "started_at": 1.0,
                "completed_at": 2.0,
            },
            db_path=act_db,
        )
        store = ActionStore(store_db)
        await store.initialize()
        await store.insert_audit(
            {
                "action_id": "knowledge_revision:store_probe",
                "entity_id": "ent-1",
                "domain_id": domain_id or "n24-domain",
                "actor": "suite",
                "result_status": "executed",
                "tenant_id": tenant_id,
                "params": {"tenant_id": tenant_id},
            }
        )
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/unified-v1.txt",
            content=b"n24-unified-v1",
            connector="n24",
            domain_id=domain_id,
            revision=1,
        )
        evidence = [
            {
                "source_id": src["source_id"],
                "locator": "x",
                "quote": "a",
                "fetched_at": src["fetched_at"],
            }
        ]
        fact = await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="locked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            revision=1,
            enforce_write_gates=False,
        )
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            subject="door",
            predicate="state",
            object="unlocked",
            evidence=evidence,
            source_policy="n24_policy",
            extractor_version="n24",
            review_status="draft",
            confidence=0.5,
            domain_id=domain_id,
            fact_id=fact["fact_id"],
            revision=2,
            enforce_write_gates=False,
            revision_actor="n24-suite",
            revision_reason="mutate",
        )

        view = await list_unified_audit_events(
            tenant_id=tenant_id,
            package_db_path=pkg_db,
            action_execution_db_path=act_db,
            action_store_db_path=store_db,
            bus_db_path=bus_db,
            fact_ledger=lg,
            limit=200,
        )
        tags = {e.get("stream") for e in view.get("events") or []}
        pkg_ok = "package" in tags and pub.get("status") == "published"
        cases.append(
            {
                "id": "package_stream_present",
                "ok": pkg_ok,
                "detail": "" if pkg_ok else "package_missing",
            }
        )
        act_ok = "action_execution" in tags
        cases.append(
            {
                "id": "action_stream_present",
                "ok": act_ok,
                "detail": "" if act_ok else "action_missing",
            }
        )
        rev_ok = "revision_audit" in tags
        cases.append(
            {
                "id": "revision_stream_present",
                "ok": rev_ok,
                "detail": "" if rev_ok else "revision_missing",
            }
        )
        store_ok = "action_store" in tags
        cases.append(
            {
                "id": "action_store_stream_present",
                "ok": store_ok,
                "detail": "" if store_ok else "action_store_missing",
            }
        )

        other = await list_unified_audit_events(
            tenant_id="other-tenant",
            package_db_path=pkg_db,
            action_execution_db_path=act_db,
            action_store_db_path=store_db,
            bus_db_path=bus_db,
            fact_ledger=lg,
            limit=50,
        )
        xt_ok = int(other.get("count") or 0) == 0
        cases.append(
            {
                "id": "cross_tenant_empty",
                "ok": xt_ok,
                "detail": "" if xt_ok else "cross_tenant_leak",
            }
        )
    finally:
        os.environ.pop("AIPLAT_UNIFIED_AUDIT_BUS_DB", None)
        tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N24_UNIFIED_AUDIT_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "unified_audit_view",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Package+Action+revision+ActionStore+bus merge; not N24 certified",
    }


def evaluate_unified_audit_view_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 统一审计视图门槛门；certified 恒 false。

    Args:
        suite: ``run_unified_audit_view_suite`` 回执。

    Returns:
        gate 字典。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        # 为什么：套件误标认证仍拒绝
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "unified_audit_view",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Unified audit view harden; not N24 certified",
    }
