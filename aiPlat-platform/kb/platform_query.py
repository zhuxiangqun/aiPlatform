"""Platform HTTP KB retrieve — structured items/citations for hybrid citation UX.

``POST /platform/kb/query`` must not rely on the prompt-type ``knowledge_query``
skill (empty items). It also must not call in-process CRAG/embedding by default:
gunicorn workers on macOS abort with objc fork safety when torch/objc loads
after fork.

Default path: local SQLite keyword / FTS on ``kb_elements`` (no heavy deps).
Optional: ``AIPLAT_KB_QUERY_CRAG=1`` switches to ``query_elements`` (CRAG).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _ensure_item_text(items: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        if not str(row.get("text") or "").strip():
            row["text"] = str(
                row.get("snippet") or row.get("full_text") or row.get("content") or ""
            )
        out.append(row)
    return out


def _extract_keywords(question: str) -> List[str]:
    q = str(question or "").strip()
    if not q:
        return []
    toks = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{2,}", q)
    # Prefer longer Chinese n-grams first; de-dupe preserve order
    seen = set()
    out: List[str] = []
    for t in sorted(toks, key=len, reverse=True):
        tl = t.lower()
        if tl in seen:
            continue
        seen.add(tl)
        out.append(t)
        if len(out) >= 8:
            break
    if not out and q:
        out = [q[:40]]
    return out


def _fts_query(keywords: List[str]) -> str:
    # FTS5: OR tokens; quote to avoid syntax errors on punctuation
    parts = []
    for k in keywords[:6]:
        safe = re.sub(r'[^\w\u4e00-\u9fff]+', "", k, flags=re.UNICODE)
        if len(safe) >= 2:
            parts.append(f'"{safe}"')
    return " OR ".join(parts)


def _score_from_rank(rank: Any) -> float:
    try:
        # FTS rank is typically negative; map to (0,1] soft score
        r = float(rank)
        if r >= 0:
            return min(1.0, max(0.01, 1.0 / (1.0 + r)))
        return min(1.0, max(0.01, 1.0 / (1.0 - r)))
    except (TypeError, ValueError):
        return 0.0


def _retrieve_local(
    *,
    tenant_id: str,
    collection_id: str,
    question: str,
    limit: int,
) -> Dict[str, Any]:
    from kb.db import KBSqlite
    from kb.storage import get_tenant_storage

    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()
    keywords = _extract_keywords(question)
    top_k = max(1, min(int(limit or 10), 50))
    rows: List[Dict[str, Any]] = []

    # 1) FTS5 when available
    fts_q = _fts_query(keywords)
    if fts_q:
        try:
            rows = db.search_fts(tenant_id=tenant_id, query=fts_q, limit=top_k * 3) or []
        except Exception:
            logger.debug("search_fts failed", exc_info=True)
            rows = []

    # 2) LIKE fallback (collection-scoped)
    if not rows and keywords:
        try:
            with db.connect() as conn:
                like_clauses = " OR ".join(["e.text LIKE ?" for _ in keywords[:5]])
                params: List[Any] = [tenant_id, collection_id or "default"]
                for k in keywords[:5]:
                    params.append(f"%{k}%")
                params.append(top_k * 3)
                sql = f"""
                    SELECT e.element_id, e.doc_id, e.type, e.page_idx, e.text, e.meta_json,
                           0 AS score
                    FROM kb_elements e
                    JOIN documents d ON d.tenant_id = e.tenant_id AND d.doc_id = e.doc_id
                    WHERE e.tenant_id = ? AND d.collection_id = ?
                      AND ({like_clauses})
                    ORDER BY e.page_idx ASC
                    LIMIT ?
                """
                rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        except Exception:
            logger.warning("keyword LIKE retrieve failed", exc_info=True)
            rows = []

    # 3) Catalog fallback: list docs when asking what is in the KB
    catalog_hit = False
    if not rows:
        qlow = question.lower()
        if any(x in question for x in ("哪些文档", "有什么文档", "文档列表", "知识库有")) or "list doc" in qlow:
            catalog_hit = True
            try:
                with db.connect() as conn:
                    docs = conn.execute(
                        """
                        SELECT doc_id, source_uri, kind, collection_id
                        FROM documents
                        WHERE tenant_id=? AND collection_id=?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (tenant_id, collection_id or "default", top_k),
                    ).fetchall()
                for d in docs:
                    dd = dict(d)
                    title = str(dd.get("source_uri") or dd.get("doc_id") or "document")
                    rows.append(
                        {
                            "element_id": None,
                            "doc_id": dd.get("doc_id"),
                            "type": "catalog",
                            "page_idx": None,
                            "text": f"文档: {title} (kind={dd.get('kind') or '-'})",
                            "score": 0.5,
                        }
                    )
            except Exception:
                logger.warning("catalog list failed", exc_info=True)

    items: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    for e in rows[:top_k]:
        did = str(e.get("doc_id") or "")
        page_idx = e.get("page_idx")
        full_text = str(e.get("text") or "").strip()
        snippet = full_text[:600]
        score = e.get("score")
        if score is None or score == 0:
            score = _score_from_rank(e.get("rank")) if e.get("rank") is not None else 0.0
        items.append(
            {
                "element_id": e.get("element_id"),
                "doc_id": did,
                "type": e.get("type"),
                "page_idx": page_idx,
                "snippet": snippet,
                "text": snippet,
                "full_text": full_text[:20000],
                "score": float(score) if isinstance(score, (int, float)) else 0.0,
                "source": did or "unknown",
            }
        )
        if did and page_idx is not None:
            citations.append(
                {
                    "doc_id": did,
                    "page_idx": int(page_idx),
                    "source": did,
                    "text": snippet[:200],
                }
            )

    if items:
        if catalog_hit:
            answer = f"当前集合共检索到 {len(items)} 篇文档条目。"
        else:
            answer = f"检索到与问题相关的内容片段 {len(items)} 条。"
            if keywords:
                answer += f" 关键词：{', '.join(keywords[:5])}。"
    else:
        answer = "知识库中未检索到与问题直接相关的文档片段。"

    return {
        "tenant_id": tenant_id,
        "collection_id": collection_id,
        "answer": answer,
        "items": items,
        "citations": citations,
        "retrieval_mode": "catalog" if catalog_hit else ("fts_or_like"),
        "generation_mode": "fallback",
        "mode": "local_keyword+fallback",
        "keywords": keywords,
    }


async def execute_platform_kb_query(
    *,
    tenant_id: str,
    collection_id: str,
    question: str,
    limit: int = 10,
    doc_id: Optional[str] = None,
    normalize_citations: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Run structured KB retrieve and shape a Pi/telemetry-friendly payload.

    ``normalize_citations`` is injectable (routes pass ``_normalize_citations_with_assets``).
    """
    tid = str(tenant_id or "default").strip() or "default"
    cid = str(collection_id or "default").strip() or "default"
    q = str(question or "").strip()
    top_k = max(1, min(int(limit or 10), 50))

    use_crag = str(os.getenv("AIPLAT_KB_QUERY_CRAG", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    data: Dict[str, Any]
    if use_crag:
        try:
            from kb.intelligence.query import query_elements

            raw = await query_elements(
                tenant_id=tid,
                collection_id=cid,
                doc_id=doc_id,
                question=q,
                top_k=top_k,
            )
            data = dict(raw) if isinstance(raw, dict) else {}
        except Exception:
            logger.warning("CRAG query_elements failed; falling back to local retrieve", exc_info=True)
            data = _retrieve_local(
                tenant_id=tid, collection_id=cid, question=q, limit=top_k
            )
    else:
        data = _retrieve_local(
            tenant_id=tid, collection_id=cid, question=q, limit=top_k
        )

    items = _ensure_item_text(
        list(data.get("items") or []) if isinstance(data.get("items"), list) else []
    )
    data = dict(data)
    data["items"] = items

    kb = data
    if normalize_citations is not None:
        try:
            normalized = normalize_citations(tenant_id=tid, data=data)
            if isinstance(normalized, dict):
                kb = normalized
                kb["items"] = _ensure_item_text(
                    list(kb.get("items") or []) if isinstance(kb.get("items"), list) else []
                )
        except Exception:
            logger.debug("normalize_citations failed", exc_info=True)
            kb = data

    answer = str(kb.get("answer") or data.get("answer") or "")
    citations = kb.get("citations") if isinstance(kb.get("citations"), list) else []
    items_out = kb.get("items") if isinstance(kb.get("items"), list) else []

    return {
        "status": "completed",
        "ok": True,
        "detail": "",
        "message": "",
        "tenant_id": tid,
        "collection_id": cid,
        "question": q,
        "answer": answer,
        "items": items_out,
        "citations": citations,
        "kb": kb,
        "retrieval_mode": kb.get("retrieval_mode") or data.get("retrieval_mode"),
        "generation_mode": kb.get("generation_mode") or data.get("generation_mode"),
        "mode": kb.get("mode") or data.get("mode"),
        "skill_id": "platform_kb_local" if not use_crag else "query_elements",
    }
