"""Fact/Query 统一审计快照（附录 N N19 deepen）。

职责：
  - 统一 Fact 变更与 Query 响应的审计快照 schema（同库同表）
  - 标记 ``runtime_authority`` 与 ActionExecution 快照字段对齐（before/after）
  - put_fact / unified_query_gateway / query_facts_gateway / query_facts list
    / MaterialsChat 直出 / GraphRAG / Wiki-KB / 裸 list syscall
    / KB Q&A（``sys_crag_retrieve`` / ``kb_qa_retrieve`` / RAG Agent）
    / 统一 ``sys_knowledge_retrieve``（会话/Builder/技能）
    / Agent ``sys_wiki_context``（信封失败兜底）
    / Wiki ``wiki_structured_query_api`` / ``wiki_search_pages_api``
    / Agent ``sys_ontology_context``（域版）
    / URN ``syscalls/ontology.py`` + HTTP ``ontology_routes``
    / ``sys_graph_neighbors`` 热路径
    best-effort 落快照（可 env 关闭）
  - 快照写入后 best-effort 追加统一审计总线（N24 J11；可 env 关）
  - 套件/门槛门：``certified`` / ``n19_full`` 恒 false

非目标：
  - 不宣称全部旁路入口已强制落盘
  - 不宣称 N24 / N19 certified
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
    "graphrag_hotpath_entry",
    "wiki_kb_hotpath_entry",
    "bare_list_hotpath_entry",
    "kb_qa_hotpath_entry",
    "knowledge_retrieve_hotpath_entry",
    "wiki_context_hotpath_entry",
    "wiki_structured_hotpath_entry",
    "ontology_context_hotpath_entry",
    "ontology_urn_hotpath_entry",
    "wiki_pages_hotpath_entry",
    "graph_neighbors_hotpath_entry",
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
    out = {
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
    # 为什么：N24 J11 — Fact/Query 热路径 best-effort 写总线；与 materialize 幂等共存
    _maybe_append_fact_query_to_bus(out)
    return out


def hotpath_audit_enabled() -> bool:
    """热路径落快照开关（默认开；``AIPLAT_FACT_QUERY_AUDIT_HOTPATH=0`` 关闭）。"""
    raw = (os.environ.get("AIPLAT_FACT_QUERY_AUDIT_HOTPATH") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def bus_hotpath_enabled() -> bool:
    """Fact/Query → 统一审计总线热路径开关（默认开；``AIPLAT_FACT_QUERY_AUDIT_BUS_HOTPATH=0`` 关）。"""
    raw = (os.environ.get("AIPLAT_FACT_QUERY_AUDIT_BUS_HOTPATH") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def _maybe_append_fact_query_to_bus(row: Dict[str, Any]) -> None:
    """N24 J11：快照写入后 best-effort 追加统一审计总线（幂等 event_id=fqa:…）。

    Args:
        row: ``record_audit_snapshot`` 回执。
    """
    if not bus_hotpath_enabled():
        return
    tid = str((row or {}).get("tenant_id") or "").strip()
    sid = str((row or {}).get("snapshot_id") or "").strip()
    if not tid or not sid:
        return
    try:
        from core.harness.knowledge_pipeline.unified_audit_bus import (
            append_unified_audit_event,
        )

        kind = str(row.get("kind") or "query")
        append_unified_audit_event(
            tenant_id=tid,
            event_id=f"fqa:{sid}",
            stream="fact_query_audit",
            event_type=kind,
            occurred_at=float(row.get("recorded_at") or time.time()),
            actor=str((row.get("meta") or {}).get("actor") or ""),
            subject=str(row.get("subject_ref") or ""),
            refs={
                "runtime_authority": row.get("runtime_authority") or "",
                "kind": kind,
            },
            payload=row,
        )
    except Exception:
        # 为什么：总线失败不得拖垮 Fact/Query 审计主路径
        logger.warning(
            "unified_audit_bus append failed for fact_query_audit %s",
            sid,
            exc_info=True,
        )


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


def maybe_record_graphrag_hotpath(
    *,
    tenant_id: str,
    result: Dict[str, Any],
    query: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """GraphRAG 旁路热路径落 Query 快照；原样返回 result。

    Args:
        tenant_id: 租户（空则跳过）。
        result: N21/N06/N20 信封后的 GraphRAG 回执。
        query: 可选原始问题摘要。
        db_path: 可选库路径。
    """
    out = result if isinstance(result, dict) else {}
    tid = (tenant_id or "").strip()
    if not tid:
        return out
    n21 = out.get("n21_query") if isinstance(out.get("n21_query"), dict) else {}
    g1 = out.get("gateway_f1") if isinstance(out.get("gateway_f1"), dict) else {}
    citations = list(n21.get("citations") or g1.get("citations") or [])[:20]
    maybe_record_hotpath_audit(
        tenant_id=tid,
        kind="query",
        subject_ref=f"gr:{uuid.uuid4().hex[:12]}",
        before_snapshot={
            "query": (query or "")[:500],
            "route": "graphrag",
            "mode": str(out.get("mode") or ""),
        },
        after_snapshot={
            "abstained": bool(
                n21.get("abstained") if "abstained" in n21 else g1.get("abstained")
            ),
            "citations": citations,
            "route_reason": "graphrag",
            "answer": str(n21.get("answer") or g1.get("answer") or "")[:500],
            "has_gateway_f1": bool(g1),
            "n21_graphrag_enforced": bool(out.get("n21_graphrag_enforced")),
            "chunk_count": len(out.get("chunks") or [])
            if isinstance(out.get("chunks"), list)
            else 0,
        },
        runtime_authority="graphrag",
        meta={
            "hotpath": True,
            "op": "graphrag_retrieve",
            "route": "graphrag",
        },
        db_path=db_path,
    )
    return out


def maybe_record_wiki_kb_hotpath(
    *,
    tenant_id: str,
    response: Dict[str, Any],
    channel: str = "wiki",
    query: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Wiki/KB 查询形与 list 信封热路径落 Query 快照；原样返回 response。

    Args:
        tenant_id: 租户（空则跳过）。
        response: N21 enforce / list 信封后的回执。
        channel: ``wiki`` / ``kb`` / ``wiki_context``。
        query: 可选原始问题摘要。
        db_path: 可选库路径。
    """
    out = response if isinstance(response, dict) else {}
    tid = (tenant_id or "").strip()
    if not tid:
        return out
    ch = (channel or "wiki").strip() or "wiki"
    n21 = out.get("n21_query") if isinstance(out.get("n21_query"), dict) else {}
    citations = list(
        out.get("citations") or n21.get("citations") or []
    )[:20]
    maybe_record_hotpath_audit(
        tenant_id=tid,
        kind="query",
        subject_ref=f"wk:{ch}:{uuid.uuid4().hex[:12]}",
        before_snapshot={
            "query": (query or "")[:500],
            "route": ch,
            "channel": ch,
        },
        after_snapshot={
            "abstained": bool(
                out.get("abstained")
                if "abstained" in out
                else n21.get("abstained")
            ),
            "citations": citations,
            "route_reason": ch,
            "answer": str(out.get("answer") or n21.get("answer") or "")[:500],
            "n21_list_enforced": bool(out.get("n21_list_enforced")),
            "n21_enforced": bool(out.get("n21_enforced") or n21),
        },
        runtime_authority="wiki_kb",
        meta={
            "hotpath": True,
            "op": "wiki_kb",
            "route": ch,
            "channel": ch,
        },
        db_path=db_path,
    )
    return out


def maybe_record_bare_list_hotpath(
    *,
    tenant_id: str,
    hits: Optional[List[Any]] = None,
    channel: str = "wiki",
    query: str = "",
    db_path: Optional[str] = None,
) -> None:
    """裸 ``sys_wiki_retrieve`` / ``sys_kb_retrieve`` list 热路径落 Query 快照。

    不改 list 主返回；上层信封路径应关 ``record_hotpath_audit`` 防双写。

    Args:
        tenant_id: 租户（空则跳过）。
        hits: 命中列表。
        channel: ``wiki`` / ``kb``。
        query: 可选原始问题摘要。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return
    rows = [h for h in (hits or []) if isinstance(h, dict)]
    ch = (channel or "wiki").strip() or "wiki"
    maybe_record_hotpath_audit(
        tenant_id=tid,
        kind="query",
        subject_ref=f"bl:{ch}:{uuid.uuid4().hex[:12]}",
        before_snapshot={
            "query": (query or "")[:500],
            "route": f"bare_{ch}",
            "channel": ch,
        },
        after_snapshot={
            "abstained": len(rows) == 0,
            "citations": [
                {
                    "source_id": str(
                        h.get("source") or h.get("source_id") or h.get("title") or ""
                    ),
                    "title": str(h.get("title") or "")[:120],
                }
                for h in rows[:20]
            ],
            "results": len(rows),
            "route_reason": f"bare_{ch}_list",
        },
        runtime_authority="bare_list_retrieve",
        meta={
            "hotpath": True,
            "op": "bare_list_retrieve",
            "route": ch,
            "channel": ch,
        },
        db_path=db_path,
    )


def maybe_record_knowledge_retrieve_hotpath(
    *,
    tenant_id: str,
    hits: Optional[List[Any]] = None,
    query: str = "",
    route: str = "rrf",
    db_path: Optional[str] = None,
) -> None:
    """统一 ``sys_knowledge_retrieve`` 热路径落 Query 快照。

    不改 list 主返回；HyDE/CRAG 等上层应关 ``record_hotpath_audit`` 防双写。

    Args:
        tenant_id: 租户（空则跳过）。
        hits: 融合后的命中列表。
        query: 可选原始问题摘要。
        route: 路由标签（``rrf`` / ``kb_only`` / ``graph_early``）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return
    rows = [h for h in (hits or []) if isinstance(h, dict)]
    rt = (route or "rrf").strip() or "rrf"
    maybe_record_hotpath_audit(
        tenant_id=tid,
        kind="query",
        subject_ref=f"kr:{uuid.uuid4().hex[:12]}",
        before_snapshot={
            "query": (query or "")[:500],
            "route": f"knowledge_retrieve_{rt}",
        },
        after_snapshot={
            "abstained": len(rows) == 0,
            "citations": [
                {
                    "source_id": str(
                        h.get("source")
                        or h.get("source_id")
                        or h.get("title")
                        or h.get("doc_id")
                        or ""
                    ),
                    "title": str(h.get("title") or "")[:120],
                    "source_type": str(h.get("source_type") or ""),
                }
                for h in rows[:20]
            ],
            "results": len(rows),
            "route_reason": f"knowledge_retrieve_{rt}",
        },
        runtime_authority="knowledge_retrieve",
        meta={
            "hotpath": True,
            "op": "knowledge_retrieve",
            "route": rt,
        },
        db_path=db_path,
    )


def maybe_record_kb_qa_hotpath(
    *,
    tenant_id: str,
    retrieved_text: str = "",
    citations: Optional[List[Any]] = None,
    query: str = "",
    route: str = "crag",
    db_path: Optional[str] = None,
) -> None:
    """KB Q&A（``sys_crag_retrieve`` / ``kb_qa_retrieve``）热路径落 Query 快照。

    不改 ``(text, citations)`` 主返回；MaterialsChat 等上层应关
    ``record_hotpath_audit`` 防双写。

    Args:
        tenant_id: 租户（空则跳过）。
        retrieved_text: 召回正文。
        citations: 引用列表。
        query: 可选原始问题摘要。
        route: 路由标签（如 ``crag`` / ``cache`` / ``graphrag``）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return
    cites_raw = [c for c in (citations or []) if isinstance(c, dict)]
    text = retrieved_text or ""
    rt = (route or "crag").strip() or "crag"
    maybe_record_hotpath_audit(
        tenant_id=tid,
        kind="query",
        subject_ref=f"kq:{uuid.uuid4().hex[:12]}",
        before_snapshot={
            "query": (query or "")[:500],
            "route": f"kb_qa_{rt}",
        },
        after_snapshot={
            "abstained": not bool(str(text).strip()) and len(cites_raw) == 0,
            "citations": [
                {
                    "source_id": str(
                        c.get("source")
                        or c.get("source_id")
                        or c.get("doc_id")
                        or ""
                    ),
                    "title": str(c.get("title") or "")[:120],
                }
                for c in cites_raw[:20]
            ],
            "results": len(cites_raw),
            "text_len": len(text),
            "route_reason": f"kb_qa_{rt}",
            "answer": str(text)[:500],
        },
        runtime_authority="kb_qa_retrieve",
        meta={
            "hotpath": True,
            "op": "kb_qa_retrieve",
            "route": rt,
        },
        db_path=db_path,
    )


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
            "MaterialsChat/GraphRAG/Wiki-KB/bare list/KB Q&A/"
            "knowledge_retrieve/wiki_context/wiki_structured/wiki_pages/"
            "ontology_context/ontology_urn/graph_neighbors hotpath; "
            "not N19 certified / not all bypass paths"
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

        from core.harness.knowledge_pipeline import query_abstain_citations as qac

        gr_src = inspect.getsource(qac.attach_graphrag_n21_envelope)
        cases.append(
            {
                "id": "graphrag_hotpath_entry",
                "ok": "maybe_record_graphrag_hotpath" in gr_src,
                "detail": "",
            }
        )

        wk_src = (
            inspect.getsource(qac.attach_list_retrieve_n21_envelope)
            + inspect.getsource(qac.query_wiki_with_abstain)
            + inspect.getsource(qac.query_kb_with_abstain)
        )
        cases.append(
            {
                "id": "wiki_kb_hotpath_entry",
                "ok": "maybe_record_wiki_kb_hotpath" in wk_src,
                "detail": "",
            }
        )

        from core.harness.syscalls import retrieval as ret

        bare_src = (
            inspect.getsource(ret.sys_kb_retrieve)
            + inspect.getsource(ret._sync_wiki_retrieve)
        )
        cases.append(
            {
                "id": "bare_list_hotpath_entry",
                "ok": "maybe_record_bare_list_hotpath" in bare_src,
                "detail": "",
            }
        )

        from core.harness.syscalls import retrieval_crag as crag

        crag_src = inspect.getsource(crag.sys_crag_retrieve)
        cases.append(
            {
                "id": "kb_qa_hotpath_entry",
                "ok": "maybe_record_kb_qa_hotpath" in crag_src,
                "detail": "",
            }
        )

        kr_src = inspect.getsource(ret.sys_knowledge_retrieve)
        cases.append(
            {
                "id": "knowledge_retrieve_hotpath_entry",
                "ok": "maybe_record_knowledge_retrieve_hotpath" in kr_src,
                "detail": "",
            }
        )

        from core.harness.syscalls import wiki_context as wc

        wc_src = inspect.getsource(wc.sys_wiki_context)
        cases.append(
            {
                "id": "wiki_context_hotpath_entry",
                "ok": (
                    "attach_list_retrieve_n21_envelope" in wc_src
                    and "maybe_record_wiki_kb_hotpath" in wc_src
                ),
                "detail": "",
            }
        )

        from core.api import core_facade as facade

        ws_src = inspect.getsource(facade.wiki_structured_query_api)
        cases.append(
            {
                "id": "wiki_structured_hotpath_entry",
                "ok": "maybe_record_wiki_kb_hotpath" in ws_src
                and "wiki_structured" in ws_src,
                "detail": "",
            }
        )

        from core.harness.syscalls import ontology_context as oc

        oc_src = inspect.getsource(oc.sys_ontology_context)
        cases.append(
            {
                "id": "ontology_context_hotpath_entry",
                "ok": (
                    "maybe_record_wiki_kb_hotpath" in oc_src
                    and "ontology_context" in oc_src
                ),
                "detail": "",
            }
        )

        from core.harness.syscalls import ontology as oc_urn
        from core.api.routers import ontology_routes as oc_http

        urn_src = (
            inspect.getsource(oc_urn.sys_ontology_context)
            + inspect.getsource(oc_http.ontology_query)
            + inspect.getsource(oc_http.ontology_impact)
            + inspect.getsource(oc_http._n19_audit)
        )
        cases.append(
            {
                "id": "ontology_urn_hotpath_entry",
                "ok": (
                    "maybe_record_wiki_kb_hotpath" in urn_src
                    and "ontology_urn" in urn_src
                ),
                "detail": "",
            }
        )

        wp_src = inspect.getsource(facade.wiki_search_pages_api)
        cases.append(
            {
                "id": "wiki_pages_hotpath_entry",
                "ok": (
                    "maybe_record_wiki_kb_hotpath" in wp_src
                    and "wiki_pages" in wp_src
                ),
                "detail": "",
            }
        )

        from core.harness.syscalls import graph as graph_sc

        gn_src = inspect.getsource(graph_sc.sys_graph_neighbors)
        cases.append(
            {
                "id": "graph_neighbors_hotpath_entry",
                "ok": (
                    "maybe_record_wiki_kb_hotpath" in gn_src
                    and "graph_neighbors" in gn_src
                ),
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
                "MaterialsChat/GraphRAG/Wiki-KB/bare list/KB Q&A/"
                "knowledge_retrieve/wiki_context/wiki_structured/wiki_pages/"
                "ontology_context/ontology_urn/graph_neighbors hotpath; "
                "not all bypass paths / not certified"
            ),
        }
    finally:
        tmp.cleanup()
