"""N24 Unified Audit Bus（Batch J5–J7）— append-only 写总线。

职责：租户隔离的统一审计事件落盘；幂等 append；从只读汇合 materialize；suite/gate 诚实锁。
非目标：不宣称 N24 certified；不改写 ActionStore 历史行。
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_N24_UNIFIED_AUDIT_BUS_CASES = (
    "append_idempotent",
    "revision_emit_to_bus",
    "package_hotpath_to_bus",
    "action_hotpath_to_bus",
    "action_store_hotpath_to_bus",
    "materialize_source_streams",
    "cross_tenant_empty",
)


def _default_db_path() -> str:
    """解析统一审计总线 DB 路径。"""
    env = (os.environ.get("AIPLAT_UNIFIED_AUDIT_BUS_DB") or "").strip()
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "unified_audit_bus.sqlite3")
    return "./data/unified_audit_bus.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化 append-only 总线表。

    Args:
        db_path: 可选库路径。
    """
    path = db_path or _default_db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS unified_audit_events (
            tenant_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            stream TEXT NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at REAL NOT NULL,
            actor TEXT,
            subject TEXT,
            refs_json TEXT,
            payload_json TEXT,
            recorded_at REAL NOT NULL,
            PRIMARY KEY (tenant_id, event_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_uab_tenant_occurred "
        "ON unified_audit_events(tenant_id, occurred_at)"
    )
    conn.commit()
    return conn


def _row_to_event(row: sqlite3.Row) -> Dict[str, Any]:
    """SQLite 行 → 统一事件字典。

    Args:
        row: 总线表行。
    """
    refs: Any = {}
    payload: Any = {}
    try:
        refs = json.loads(row["refs_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        refs = {}
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    return {
        "tenant_id": row["tenant_id"],
        "event_id": row["event_id"],
        "stream": row["stream"],
        "event_type": row["event_type"],
        "occurred_at": float(row["occurred_at"] or 0.0),
        "actor": row["actor"] or "",
        "subject": row["subject"] or "",
        "refs": refs if isinstance(refs, dict) else {},
        "payload": payload if isinstance(payload, dict) else {},
        "recorded_at": float(row["recorded_at"] or 0.0),
    }


def append_unified_audit_event(
    *,
    tenant_id: str,
    event_id: str,
    stream: str,
    event_type: str,
    occurred_at: float = 0.0,
    actor: str = "",
    subject: str = "",
    refs: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """追加一条统一审计事件（同 tenant+event_id 幂等，不覆盖）。

    Args:
        tenant_id: 租户（必填）。
        event_id: 事件主键（必填；幂等键）。
        stream: 源流水线名（如 revision_audit / package）。
        event_type: 事件类型。
        occurred_at: 业务发生时间（epoch float）。
        actor: 操作者。
        subject: 主体摘要。
        refs: 引用字典。
        payload: 原始载荷。
        db_path: 可选 DB。

    Returns:
        事件字典；已存在时返回库中行并标记 ``idempotent_hit=True``。

    Raises:
        ValueError: 缺必填字段。
    """
    tid = (tenant_id or "").strip()
    eid = (event_id or "").strip()
    st = (stream or "").strip()
    et = (event_type or "").strip()
    if not tid or not eid or not st or not et:
        raise ValueError("tenant_id/event_id/stream/event_type required")
    try:
        occ = float(occurred_at or 0.0)
    except (TypeError, ValueError):
        occ = 0.0
    recorded = time.time()
    refs_obj = dict(refs or {})
    payload_obj = dict(payload or {})
    conn = _connect(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM unified_audit_events WHERE tenant_id=? AND event_id=?",
            (tid, eid),
        ).fetchone()
        if existing is not None:
            out = _row_to_event(existing)
            out["idempotent_hit"] = True
            return out
        conn.execute(
            """
            INSERT INTO unified_audit_events (
                tenant_id, event_id, stream, event_type, occurred_at,
                actor, subject, refs_json, payload_json, recorded_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                tid,
                eid,
                st,
                et,
                occ,
                (actor or "").strip(),
                (subject or "").strip(),
                json.dumps(refs_obj, ensure_ascii=False, default=str),
                json.dumps(payload_obj, ensure_ascii=False, default=str),
                recorded,
            ),
        )
        conn.commit()
        return {
            "tenant_id": tid,
            "event_id": eid,
            "stream": st,
            "event_type": et,
            "occurred_at": occ,
            "actor": (actor or "").strip(),
            "subject": (subject or "").strip(),
            "refs": refs_obj,
            "payload": payload_obj,
            "recorded_at": recorded,
            "idempotent_hit": False,
        }
    finally:
        conn.close()


def list_unified_audit_bus_events(
    *,
    tenant_id: str,
    stream: str = "",
    event_type: str = "",
    limit: int = 100,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """按租户列出总线事件（可选 stream/event_type 过滤）。

    Args:
        tenant_id: 租户（必填）。
        stream: 可选源流水线过滤。
        event_type: 可选事件类型。
        limit: 最大条数（1–500）。
        db_path: 可选 DB。

    Returns:
        按 occurred_at 升序的事件列表。

    Raises:
        ValueError: tenant_id 为空。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id required")
    lim = max(1, min(int(limit or 100), 500))
    clauses = ["tenant_id=?"]
    params: List[Any] = [tid]
    st = (stream or "").strip()
    et = (event_type or "").strip()
    if st:
        clauses.append("stream=?")
        params.append(st)
    if et:
        clauses.append("event_type=?")
        params.append(et)
    where = " AND ".join(clauses)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM unified_audit_events
            WHERE {where}
            ORDER BY occurred_at ASC, event_id ASC
            LIMIT ?
            """,
            (*params, lim),
        ).fetchall()
        return [_row_to_event(r) for r in rows]
    finally:
        conn.close()


async def materialize_unified_audit_from_view(
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
    """将只读源流水合写入总线（certified 恒 false）。

    Args:
        tenant_id: 租户。
        streams: 源流水线；默认含 package/action/revision/action_store（不含 bus）。
        package_id: Package 可选过滤。
        action_id_prefix: Action 可选前缀。
        entity_type: revision 可选实体类型。
        entity_id: revision 可选实体 ID。
        domain_id: ActionStore 可选域过滤。
        limit: 源侧最大条数。
        package_db_path: Package DB。
        action_execution_db_path: ActionExecution DB。
        action_store_db_path: ActionStore DB。
        bus_db_path: 总线 DB。
        fact_ledger: 可选 FactLedger。

    Returns:
        ``{written, skipped, events, certified:false, ...}``。
    """
    from core.harness.knowledge_pipeline.unified_audit_view import (
        list_unified_audit_events,
    )

    # 为什么：materialize 只吃源流水，禁止把 bus 再写回 bus
    src_streams = [str(s).strip() for s in (streams or ()) if str(s).strip()]
    if not src_streams:
        src_streams = [
            "package",
            "action_execution",
            "revision_audit",
            "action_store",
        ]
    src_streams = [s for s in src_streams if s != "bus"]
    if not src_streams:
        raise ValueError("streams must include at least one source stream")

    view = await list_unified_audit_events(
        tenant_id=tenant_id,
        streams=src_streams,
        package_id=package_id,
        action_id_prefix=action_id_prefix,
        entity_type=entity_type,
        entity_id=entity_id,
        domain_id=domain_id,
        limit=limit,
        package_db_path=package_db_path,
        action_execution_db_path=action_execution_db_path,
        action_store_db_path=action_store_db_path,
        fact_ledger=fact_ledger,
    )
    written = 0
    skipped = 0
    out_events: List[Dict[str, Any]] = []
    for ev in view.get("events") or []:
        eid = str(ev.get("event_id") or "").strip()
        if not eid:
            skipped += 1
            continue
        row = append_unified_audit_event(
            tenant_id=tenant_id,
            event_id=eid,
            stream=str(ev.get("stream") or "unknown"),
            event_type=str(ev.get("event_type") or "unknown"),
            occurred_at=float(ev.get("occurred_at") or 0.0),
            actor=str(ev.get("actor") or ""),
            subject=str(ev.get("subject") or ""),
            refs=dict(ev.get("refs") or {}),
            payload=dict(ev.get("payload") or {}),
            db_path=bus_db_path,
        )
        if row.get("idempotent_hit"):
            skipped += 1
        else:
            written += 1
        out_events.append(row)
    return {
        "written": written,
        "skipped": skipped,
        "count": len(out_events),
        "events": out_events,
        "source_streams": src_streams,
        "tenant_id": tenant_id,
        "certified": False,
        "n24_full_conformance": False,
        "note": "materialize into append-only bus; not ActionStore merge / not N24 certified",
    }


async def run_unified_audit_bus_suite(
    *,
    tenant_id: str = "n24-unified-audit-bus-tenant",
    domain_id: str = "",
) -> Dict[str, Any]:
    """N24 统一审计写总线最小套件（certified 恒 false）。

    Args:
        tenant_id: 写入租户。
        domain_id: 可选域（透传 FactLedger）。

    Returns:
        套件汇总。
    """
    from core.harness.infrastructure.action_execution import persist_execution
    from core.harness.knowledge_pipeline.fact_ledger import FactLedger
    from core.harness.knowledge_pipeline.ontology_package import publish_package

    tmp = tempfile.TemporaryDirectory(prefix="n24-unified-audit-bus-")
    cases: List[Dict[str, Any]] = []
    try:
        root = Path(tmp.name)
        bus_db = str(root / "unified_audit_bus.sqlite3")
        pkg_db = str(root / "ontology_package.sqlite3")
        act_db = str(root / "action_execution.sqlite3")
        os.environ["AIPLAT_UNIFIED_AUDIT_BUS_DB"] = bus_db
        lg = FactLedger(
            db_path=str(root / "fact_ledger.sqlite3"),
            raw_dir=root / "raw",
            action_execution_db_path=act_db,
        )
        await lg.initialize()

        first = append_unified_audit_event(
            tenant_id=tenant_id,
            event_id="uab-probe-1",
            stream="manual",
            event_type="probe",
            occurred_at=1.0,
            actor="suite",
            subject="probe",
            db_path=bus_db,
        )
        second = append_unified_audit_event(
            tenant_id=tenant_id,
            event_id="uab-probe-1",
            stream="manual",
            event_type="probe-changed",
            occurred_at=9.0,
            actor="suite",
            subject="probe",
            db_path=bus_db,
        )
        idemp_ok = (
            first.get("idempotent_hit") is False
            and second.get("idempotent_hit") is True
            and second.get("event_type") == "probe"
        )
        cases.append(
            {
                "id": "append_idempotent",
                "ok": idemp_ok,
                "detail": "" if idemp_ok else "idempotent_failed",
            }
        )

        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n24-kb",
            kind="file",
            uri="file://n24/uab-v1.txt",
            content=b"n24-uab-v1",
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
        bus_rows = list_unified_audit_bus_events(
            tenant_id=tenant_id, stream="revision_audit", limit=50, db_path=bus_db
        )
        rev_ok = len(bus_rows) >= 1
        cases.append(
            {
                "id": "revision_emit_to_bus",
                "ok": rev_ok,
                "detail": "" if rev_ok else "revision_not_on_bus",
            }
        )

        pub = publish_package(
            tenant_id=tenant_id,
            package_id="n24-pkg",
            version="1.0.0",
            schema=["InstallOrder"],
            db_path=pkg_db,
        )
        pkg_rows = list_unified_audit_bus_events(
            tenant_id=tenant_id, stream="package", limit=50, db_path=bus_db
        )
        pkg_ok = pub.get("status") == "published" and any(
            e.get("event_id") == "pkg:n24-pkg:1.0.0" for e in pkg_rows
        )
        cases.append(
            {
                "id": "package_hotpath_to_bus",
                "ok": pkg_ok,
                "detail": "" if pkg_ok else "package_hotpath_missing",
            }
        )

        act = persist_execution(
            {
                "tenant_id": tenant_id,
                "idempotency_key": "n24-uab-act-1",
                "action_id": "knowledge_revision:suite_probe",
                "actor": "suite",
                "status": "succeeded",
                "started_at": 1.0,
                "completed_at": 2.0,
            },
            db_path=act_db,
        )
        act_rows = list_unified_audit_bus_events(
            tenant_id=tenant_id, stream="action_execution", limit=50, db_path=bus_db
        )
        act_eid = str(act.get("execution_id") or "")
        act_ok = bool(act_eid) and any(e.get("event_id") == act_eid for e in act_rows)
        cases.append(
            {
                "id": "action_hotpath_to_bus",
                "ok": act_ok,
                "detail": "" if act_ok else "action_hotpath_missing",
            }
        )

        from core.harness.infrastructure.action_store import ActionStore

        store_db = str(root / "action_store.sqlite3")
        store = ActionStore(store_db)
        await store.initialize()
        store_aid = await store.insert_audit(
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
        store_rows = list_unified_audit_bus_events(
            tenant_id=tenant_id, stream="action_store", limit=50, db_path=bus_db
        )
        store_ok = any(e.get("event_id") == str(store_aid) for e in store_rows)
        cases.append(
            {
                "id": "action_store_hotpath_to_bus",
                "ok": store_ok,
                "detail": "" if store_ok else "action_store_hotpath_missing",
            }
        )

        mat = await materialize_unified_audit_from_view(
            tenant_id=tenant_id,
            package_db_path=pkg_db,
            action_execution_db_path=act_db,
            action_store_db_path=store_db,
            bus_db_path=bus_db,
            fact_ledger=lg,
            limit=200,
        )
        all_bus = list_unified_audit_bus_events(
            tenant_id=tenant_id, limit=200, db_path=bus_db
        )
        tags = {e.get("stream") for e in all_bus}
        # 热路径已写入时 materialize 多为幂等 skip；源标签仍须齐全
        mat_ok = (
            int(mat.get("written") or 0) + int(mat.get("skipped") or 0) >= 1
            and "package" in tags
            and "action_execution" in tags
            and "revision_audit" in tags
            and "action_store" in tags
        )
        cases.append(
            {
                "id": "materialize_source_streams",
                "ok": mat_ok,
                "detail": "" if mat_ok else f"tags={sorted(tags)} written={mat.get('written')}",
            }
        )

        other = list_unified_audit_bus_events(
            tenant_id="other-tenant", limit=50, db_path=bus_db
        )
        xt_ok = len(other) == 0
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
    required = list(_N24_UNIFIED_AUDIT_BUS_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "unified_audit_bus",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "note": "append-only bus + Package/Action/revision/ActionStore hot-path; not N24 certified",
    }


def evaluate_unified_audit_bus_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N24 统一审计写总线门槛门；certified 恒 false。

    Args:
        suite: ``run_unified_audit_bus_suite`` 回执。

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
        "gate": "unified_audit_bus",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "note": "Unified audit bus harden; not N24 certified",
    }
