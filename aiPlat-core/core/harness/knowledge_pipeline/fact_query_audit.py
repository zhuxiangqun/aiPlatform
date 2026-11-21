"""Fact/Query 统一审计快照（附录 N N19 deepen）。

职责：
  - 统一 Fact 变更与 Query 响应的审计快照 schema（同库同表）
  - 标记 ``runtime_authority`` 与 ActionExecution 快照字段对齐（before/after）
  - put_fact / unified_query_gateway / query_facts_gateway / query_facts list
    / MaterialsChat 直出热路径 best-effort 落快照（可 env 关闭）
  - 套件/门槛门：``certified`` / ``n19_full`` 恒 false

非目标：
  - 不宣称全部旁路入口（其它 Agent 等）已强制落盘
  - 不合并 Package+Action 全量审计总线（N24）
  - 不宣称 N19 certified
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SUITE_CASES = (
    "fact_snapshot_written",
    "query_snapshot_written",
    "unified_schema",
    "tenant_scoped_list",
    "runtime_authority_flag",
    "honesty_certified_false",
    "hotpath_helper_writes",
    "put_fact_hotpath_entry",
    "query_gateway_hotpath_entry",
    "query_facts_gateway_hotpath_entry",
    "query_facts_list_hotpath_entry",
    "materials_chat_hotpath_entry",
)

_KINDS = frozenset({"fact", "query"})


class FactQueryAuditError(ValueError):
    """Fact/Query 审计快照契约错误。"""


def _default_db_path() -> str:
    """解析 Fact/Query 审计库路径。"""
    env = os.environ.get("AIPLAT_FACT_QUERY_AUDIT_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "fact_query_audit.sqlite3")
    return "./data/fact_query_audit.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化统一审计快照表。

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
        CREATE TABLE IF NOT EXISTS fact_query_audit (
            snapshot_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            subject_ref TEXT NOT NULL,
            before_snapshot TEXT NOT NULL,
            after_snapshot TEXT NOT NULL,
            runtime_authority TEXT NOT NULL,
            meta_json TEXT NOT NULL,
            recorded_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fqa_tenant_kind "
        "ON fact_query_audit(tenant_id, kind, recorded_at DESC)"
    )
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """行转统一快照 dict。

    Args:
        row: SQLite 行。
    """
    return {
        "snapshot_id": row["snapshot_id"],
        "tenant_id": row["tenant_id"],
        "kind": row["kind"],
        "subject_ref": row["subject_ref"],
        "before_snapshot": json.loads(row["before_snapshot"] or "{}"),
        "after_snapshot": json.loads(row["after_snapshot"] or "{}"),
        "runtime_authority": row["runtime_authority"],
        "meta": json.loads(row["meta_json"] or "{}"),
        "recorded_at": row["recorded_at"],
        "certified": False,
        "n19_full_conformance": False,
    }


def record_audit_snapshot(
    *,
    tenant_id: str,
    kind: str,
    subject_ref: str,
    before_snapshot: Optional[Dict[str, Any]] = None,
    after_snapshot: Optional[Dict[str, Any]] = None,
    runtime_authority: str = "fact_ledger",
    meta: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """写入统一 Fact/Query 审计快照。

    Args:
        tenant_id: 租户。
        kind: ``fact`` 或 ``query``。
        subject_ref: 主体引用（fact_id / query_id）。
        before_snapshot: 变更前或查询前上下文。
        after_snapshot: 变更后或查询响应信封。
        runtime_authority: 运行时权威标识（如 fact_ledger / query_gateway）。
        meta: 可选元数据。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    k = (kind or "").strip().lower()
    subj = (subject_ref or "").strip()
    auth = (runtime_authority or "").strip()
    if not tid or not subj or not auth:
        raise FactQueryAuditError("tenant_subject_authority_required")
    if k not in _KINDS:
        raise FactQueryAuditError("kind_must_be_fact_or_query")
    before = before_snapshot if isinstance(before_snapshot, dict) else {}
    after = after_snapshot if isinstance(after_snapshot, dict) else {}
    # 为什么：与 ActionExecution 对齐——客户动作必填 before/after；Fact/Query 同约束
    if k == "fact" and not after:
        raise FactQueryAuditError("fact_after_snapshot_required")
    if k == "query" and not after:
        raise FactQueryAuditError("query_after_snapshot_required")
    sid = f"fqa-{uuid.uuid4().hex[:16]}"
    now = time.time()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO fact_query_audit(
                snapshot_id, tenant_id, kind, subject_ref,
                before_snapshot, after_snapshot, runtime_authority,
                meta_json, recorded_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                sid,
                tid,
                k,
                subj,
                json.dumps(before, ensure_ascii=False),
                json.dumps(after, ensure_ascii=False),
                auth,
                json.dumps(meta or {}, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "snapshot_id": sid,
        "tenant_id": tid,
        "kind": k,
        "subject_ref": subj,
        "before_snapshot": before,
        "after_snapshot": after,
        "runtime_authority": auth,
        "meta": meta or {},
        "recorded_at": now,
        "certified": False,
        "n19_full_conformance": False,
    }


def hotpath_audit_enabled() -> bool:
    """热路径落快照开关（默认开；``AIPLAT_FACT_QUERY_AUDIT_HOTPATH=0`` 关闭）。"""
    raw = (os.environ.get("AIPLAT_FACT_QUERY_AUDIT_HOTPATH") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def _fact_slice(rec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """热路径 Fact 快照瘦身（避免整段 evidence 膨胀）。

    Args:
        rec: Fact 记录或 None。
    """
    if not isinstance(rec, dict):
        return {}
    return {
        "fact_id": rec.get("fact_id"),
        "review_status": rec.get("review_status"),
        "status": rec.get("status"),
        "revision": rec.get("revision"),
        "subject": rec.get("subject"),
        "predicate": rec.get("predicate"),
        "object": rec.get("object"),
    }


def maybe_record_hotpath_audit(
    *,
    tenant_id: str,
    kind: str,
    subject_ref: str,
    before_snapshot: Optional[Dict[str, Any]] = None,
    after_snapshot: Optional[Dict[str, Any]] = None,
    runtime_authority: str = "fact_ledger",
    meta: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """热路径 best-effort 写审计快照；失败不抛、不阻断主路径。

    Args:
        tenant_id: 租户。
        kind: ``fact`` / ``query``。
        subject_ref: 主体引用。
        before_snapshot: 变更前/查询前。
        after_snapshot: 变更后/查询响应。
        runtime_authority: 运行时权威。
        meta: 可选元数据（建议含 ``hotpath: True``）。
        db_path: 可选库路径。
    """
    if not hotpath_audit_enabled():
        return None
    try:
        m = dict(meta or {})
        m.setdefault("hotpath", True)
        return record_audit_snapshot(
            tenant_id=tenant_id,
            kind=kind,
            subject_ref=subject_ref,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            runtime_authority=runtime_authority,
            meta=m,
            db_path=db_path,
        )
    except Exception as exc:
        # 为什么：审计不得拖垮 put_fact / Gateway 主路径
        logger.warning("fact_query_audit hotpath failed: %s", exc, exc_info=True)
        return None


def maybe_record_put_fact_hotpath(
    *,
    tenant_id: str,
    before: Optional[Dict[str, Any]],
    after: Dict[str, Any],
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """put_fact 热路径落 Fact 快照。

    Args:
        tenant_id: 租户。
        before: 写入前记录（新建则为 None）。
        after: 写入后记录。
        db_path: 可选库路径。
    """
    fid = str((after or {}).get("fact_id") or "").strip()
    if not fid:
        return None
    return maybe_record_hotpath_audit(
        tenant_id=tenant_id,
        kind="fact",
        subject_ref=fid,
        before_snapshot=_fact_slice(before),
        after_snapshot=_fact_slice(after),
        runtime_authority="fact_ledger",
        meta={"hotpath": True, "op": "put_fact"},
        db_path=db_path,
    )


def maybe_record_query_gateway_hotpath(
    *,
    tenant_id: str,
    route: str,
    query: str,
    response: Dict[str, Any],
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """unified_query_gateway 热路径落 Query 快照；原样返回 response。

    Args:
        tenant_id: 租户。
        route: Gateway 路由名。
        query: 原始查询。
        response: F.1 信封。
        db_path: 可选库路径。
    """
    resp = response if isinstance(response, dict) else {}
    r = (route or "").strip() or "unknown"
    maybe_record_hotpath_audit(
        tenant_id=tenant_id,
        kind="query",
        subject_ref=f"ug:{r}:{uuid.uuid4().hex[:12]}",
        before_snapshot={"query": query or "", "route": r},
        after_snapshot={
            "abstained": bool(resp.get("abstained")),
            "citations": list(resp.get("citations") or [])[:20],
            "route_reason": str(resp.get("route_reason") or ""),
            "answer": str(resp.get("answer") or "")[:500],
            "gateway_contract_ok": resp.get("gateway_contract_ok"),
        },
        runtime_authority="query_gateway",
        meta={"hotpath": True, "op": "unified_query_gateway", "route": r},
        db_path=db_path,
    )
    return resp


def maybe_record_query_facts_gateway_hotpath(
    *,
    tenant_id: str,
    query: str,
    response: Dict[str, Any],
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """query_facts_gateway 旁路热路径落 Query 快照；原样返回 response。

    Args:
        tenant_id: 租户。
        query: 原始查询。
        response: F.1 形响应。
        db_path: 可选库路径。
    """
    resp = response if isinstance(response, dict) else {}
    maybe_record_hotpath_audit(
        tenant_id=tenant_id,
        kind="query",
        subject_ref=f"qfg:{uuid.uuid4().hex[:12]}",
        before_snapshot={"query": query or "", "route": "fact"},
        after_snapshot={
            "abstained": bool(resp.get("abstained")),
            "citations": list(resp.get("citations") or [])[:20],
            "route_reason": str(resp.get("route_reason") or ""),
            "answer": str(resp.get("answer") or "")[:500],
            "gateway_contract_ok": resp.get("gateway_contract_ok"),
        },
        runtime_authority="query_gateway",
        meta={"hotpath": True, "op": "query_facts_gateway", "route": "fact"},
        db_path=db_path,
    )
    return resp


def maybe_record_query_facts_list_hotpath(
    *,
    tenant_id: str,
    hits: Optional[List[Dict[str, Any]]],
    filters: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> None:
    """query_facts list 旁路热路径落 Query 快照；不改返回列表。

    Args:
        tenant_id: 租户。
        hits: Fact 列表。
        filters: 查询过滤摘要。
        db_path: 可选库路径。
    """
    rows = [h for h in (hits or []) if isinstance(h, dict)]
    maybe_record_hotpath_audit(
        tenant_id=tenant_id,
        kind="query",
        subject_ref=f"qfl:{uuid.uuid4().hex[:12]}",
        before_snapshot={"filters": dict(filters or {}), "route": "fact_list"},
        after_snapshot={
            "abstained": len(rows) == 0,
            "citations": [
                {
                    "fact_id": str(h.get("fact_id") or ""),
                    "source_id": str(
                        ((h.get("evidence") or [{}])[0] or {}).get("source_id") or ""
                    ),
                }
                for h in rows[:20]
            ],
            "results": len(rows),
            "route_reason": "fact_list",
        },
        runtime_authority="fact_ledger",
        meta={"hotpath": True, "op": "query_facts", "route": "fact_list"},
        db_path=db_path,
    )


def maybe_record_materials_chat_hotpath(
    *,
    tenant_id: str,
    output: Dict[str, Any],
    exit_kind: str = "rag",
    query: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """MaterialsChat 直出旁路热路径落 Query 快照；原样返回 output。

    Args:
        tenant_id: 租户（空则跳过）。
        output: N21 enforce 后的 Agent 输出。
        exit_kind: ``rag`` / ``shortcut`` / ``cache_hit``。
        query: 可选原始问题摘要。
        db_path: 可选库路径。
    """
    out = output if isinstance(output, dict) else {}
    tid = (tenant_id or "").strip()
    if not tid:
        return out
    kind = (exit_kind or "rag").strip() or "rag"
    g1 = out.get("gateway_f1") if isinstance(out.get("gateway_f1"), dict) else {}
    citations = list(out.get("citations") or g1.get("citations") or [])[:20]
    maybe_record_hotpath_audit(
        tenant_id=tid,
        kind="query",
        subject_ref=f"mc:{kind}:{uuid.uuid4().hex[:12]}",
        before_snapshot={
            "query": (query or "")[:500],
            "route": "materials_chat",
            "exit": kind,
        },
        after_snapshot={
            "abstained": bool(out.get("abstained") if "abstained" in out else g1.get("abstained")),
            "citations": citations,
            "route_reason": f"materials_chat_{kind}",
            "answer": str(out.get("answer") or g1.get("answer") or "")[:500],
            "has_gateway_f1": bool(g1),
            "n21_enforced": bool(out.get("n21_enforced")),
        },
        runtime_authority="materials_chat",
        meta={
            "hotpath": True,
            "op": "materials_chat",
            "route": "materials_chat",
            "exit": kind,
        },
        db_path=db_path,
    )
    return out


def list_audit_snapshots(
    *,
    tenant_id: str,
    kind: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """按租户列出统一审计快照。

    Args:
        tenant_id: 租户（必填）。
        kind: 可选 ``fact``/``query``。
        limit: 上限。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        raise FactQueryAuditError("tenant_id_required")
    k = (kind or "").strip().lower()
    if k and k not in _KINDS:
        raise FactQueryAuditError("kind_must_be_fact_or_query")
    lim = max(1, min(int(limit), 200))
    conn = _connect(db_path)
    try:
        if k:
            cur = conn.execute(
                """
                SELECT * FROM fact_query_audit
                WHERE tenant_id=? AND kind=?
                ORDER BY recorded_at DESC LIMIT ?
                """,
                (tid, k, lim),
            )
        else:
            cur = conn.execute(
                """
                SELECT * FROM fact_query_audit
                WHERE tenant_id=?
                ORDER BY recorded_at DESC LIMIT ?
                """,
                (tid, lim),
            )
        items = [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return {
        "ok": True,
        "tenant_id": tid,
        "kind": k or "",
        "count": len(items),
        "items": items,
        "certified": False,
        "n19_full_conformance": False,
    }


def evaluate_fact_query_audit_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N19 deepen 门槛门（certified / n19_full 恒 false）。

    Args:
        suite: ``run_fact_query_audit_suite`` 回执。
    """
    s = suite or {}
    issues: List[str] = []
    # 为什么：禁止套件自签 certified（统一快照 deepen ≠ N19 全量认证）
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n19_full_conformance") is True:
        issues.append("honesty_n19_full_flag_forbidden")
    cases = s.get("cases") or []
    if cases:
        failed = [c for c in cases if isinstance(c, dict) and not c.get("ok")]
        if failed:
            issues.append(f"suite_cases_failed:{len(failed)}")
        ids = {str(c.get("id") or "") for c in cases if isinstance(c, dict)}
        missing = [x for x in _SUITE_CASES if x not in ids]
        if missing:
            issues.append(f"suite_cases_missing:{','.join(missing)}")
    elif not s.get("ok"):
        issues.append("suite_not_ok")
    return {
        "ok": not issues and bool(s.get("ok", True)),
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n19_full_conformance": False,
        "note": (
            "Fact/Query audit + put_fact/unified/query_facts(_gateway)/"
            "MaterialsChat hotpath; not N19 certified / not all bypass paths"
        ),
    }


def run_fact_query_audit_suite(
    *,
    tenant_id: str = "n19-fqa-tenant",
) -> Dict[str, Any]:
    """N19 deepen：Fact/Query 统一审计套件（certified 恒 false）。

    Args:
        tenant_id: 租户。
    """
    import inspect

    from core.harness.knowledge_pipeline import fact_ledger as fl

    tmp = tempfile.TemporaryDirectory(prefix="n19-fqa-")
    db = str(Path(tmp.name) / "fqa.sqlite3")
    cases: List[Dict[str, Any]] = []
    try:
        fact = record_audit_snapshot(
            tenant_id=tenant_id,
            kind="fact",
            subject_ref="fact-n19-1",
            before_snapshot={"review_status": "reviewed", "status": "draft"},
            after_snapshot={"review_status": "published", "status": "active"},
            runtime_authority="fact_ledger",
            meta={"predicate": "status"},
            db_path=db,
        )
        cases.append(
            {
                "id": "fact_snapshot_written",
                "ok": bool(fact.get("snapshot_id"))
                and fact.get("kind") == "fact"
                and fact.get("after_snapshot", {}).get("status") == "active",
                "detail": "",
            }
        )

        query = record_audit_snapshot(
            tenant_id=tenant_id,
            kind="query",
            subject_ref="query-n19-1",
            before_snapshot={"query": "status open"},
            after_snapshot={
                "abstained": False,
                "citations": [{"source_id": "s1"}],
                "results": 1,
            },
            runtime_authority="query_gateway",
            db_path=db,
        )
        cases.append(
            {
                "id": "query_snapshot_written",
                "ok": query.get("kind") == "query"
                and isinstance(query.get("after_snapshot"), dict)
                and "citations" in (query.get("after_snapshot") or {}),
                "detail": "",
            }
        )

        # 统一 schema：两行同表同字段
        listed = list_audit_snapshots(tenant_id=tenant_id, db_path=db)
        keys_ok = True
        for item in listed.get("items") or []:
            for key in (
                "snapshot_id",
                "tenant_id",
                "kind",
                "before_snapshot",
                "after_snapshot",
                "runtime_authority",
            ):
                if key not in item:
                    keys_ok = False
        kinds = {i.get("kind") for i in (listed.get("items") or [])}
        cases.append(
            {
                "id": "unified_schema",
                "ok": keys_ok and kinds == {"fact", "query"},
                "detail": "",
            }
        )

        other = list_audit_snapshots(
            tenant_id=f"{tenant_id}-other",
            db_path=db,
        )
        cases.append(
            {
                "id": "tenant_scoped_list",
                "ok": listed.get("count") == 2 and other.get("count") == 0,
                "detail": "",
            }
        )

        cases.append(
            {
                "id": "runtime_authority_flag",
                "ok": fact.get("runtime_authority") == "fact_ledger"
                and query.get("runtime_authority") == "query_gateway",
                "detail": "",
            }
        )
        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": fact.get("certified") is False
                and listed.get("n19_full_conformance") is False,
                "detail": "",
            }
        )

        hp = maybe_record_hotpath_audit(
            tenant_id=tenant_id,
            kind="query",
            subject_ref="hotpath-n19-1",
            before_snapshot={"query": "hotpath probe"},
            after_snapshot={"abstained": True, "citations": []},
            runtime_authority="query_gateway",
            meta={"hotpath": True, "probe": "suite"},
            db_path=db,
        )
        listed_hp = list_audit_snapshots(tenant_id=tenant_id, db_path=db)
        cases.append(
            {
                "id": "hotpath_helper_writes",
                "ok": bool(hp and hp.get("snapshot_id"))
                and any(
                    (i.get("meta") or {}).get("hotpath") is True
                    for i in (listed_hp.get("items") or [])
                ),
                "detail": "",
            }
        )

        put_src = inspect.getsource(fl.FactLedger.put_fact)
        ug_src = inspect.getsource(fl.unified_query_gateway)
        qfg_src = inspect.getsource(fl.FactLedger.query_facts_gateway)
        qfl_src = inspect.getsource(fl.FactLedger.query_facts)
        from core.apps.agents import materials_chat as mc

        mc_src = (
            inspect.getsource(mc._n21_enforce_rag_output)
            + inspect.getsource(mc._n21_enforce_shortcut_output)
            + inspect.getsource(mc._n21_enforce_cache_hit_output)
        )
        cases.append(
            {
                "id": "put_fact_hotpath_entry",
                "ok": "maybe_record_put_fact_hotpath" in put_src,
                "detail": "",
            }
        )
        cases.append(
            {
                "id": "query_gateway_hotpath_entry",
                "ok": "maybe_record_query_gateway_hotpath" in ug_src,
                "detail": "",
            }
        )
        cases.append(
            {
                "id": "query_facts_gateway_hotpath_entry",
                "ok": "maybe_record_query_facts_gateway_hotpath" in qfg_src,
                "detail": "",
            }
        )
        cases.append(
            {
                "id": "query_facts_list_hotpath_entry",
                "ok": "maybe_record_query_facts_list_hotpath" in qfl_src,
                "detail": "",
            }
        )
        cases.append(
            {
                "id": "materials_chat_hotpath_entry",
                "ok": "maybe_record_materials_chat_hotpath" in mc_src,
                "detail": "",
            }
        )

        passed = sum(1 for c in cases if c.get("ok"))
        return {
            "ok": passed == len(_SUITE_CASES),
            "passed": passed,
            "total": len(_SUITE_CASES),
            "cases": cases,
            "listed": listed_hp,
            "certified": False,
            "n19_full_conformance": False,
            "note": (
                "Fact/Query audit + put_fact/unified/query_facts(_gateway)/"
                "MaterialsChat hotpath; not all bypass paths / not certified"
            ),
        }
    finally:
        tmp.cleanup()
