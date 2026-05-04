from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from core.apps.document_intelligence.embeddings import cosine_similarity, embed_text
from core.apps.document_intelligence.llm import chat_complete, llm_enabled
from core.apps.document_intelligence import video_retrieval as _video_retrieval
from core.apps.multimodal_kb.db import KBSqlite
from core.apps.multimodal_kb.storage import get_tenant_storage


def _extract_keywords(q: str) -> List[str]:
    q = (q or "").strip()
    if not q:
        return []
    # Extract CJK sequences and alnum tokens.
    toks = []
    toks += re.findall(r"[A-Za-z0-9_]{2,}", q)
    toks += re.findall(r"[\u4e00-\u9fff]{2,}", q)
    # Deduplicate while preserving order.
    seen = set()
    out = []
    for t in toks:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out[:20]


def _score_text(text: str, keywords: List[str]) -> int:
    if not text or not keywords:
        return 0
    t = text.lower()
    s = 0
    for k in keywords:
        kk = k.lower()
        # simple occurrence count
        s += t.count(kk) * max(1, len(kk) // 2)
    return s


def _text_quality_score(text: str) -> float:
    s = str(text or "").strip()
    if not s:
        return 0.0
    total = len(s)
    if total == 0:
        return 0.0
    useful = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", s))
    symbol = len(re.findall(r"[^A-Za-z0-9\u4e00-\u9fff\s]", s))
    useful_ratio = useful / total
    symbol_ratio = symbol / total
    return useful_ratio - symbol_ratio * 0.7


def _is_low_quality_video_ocr(text: str) -> bool:
    s = str(text or "").strip()
    if len(s) < 8:
        return True
    if _text_quality_score(s) < 0.28:
        return True
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    latin = len(re.findall(r"[A-Za-z]", s))
    digit = len(re.findall(r"[0-9]", s))
    useful = cjk + latin + digit
    return useful < max(6, len(s) // 4)


def _element_source(e: Dict[str, Any]) -> str:
    meta = e.get("meta")
    if isinstance(meta, dict):
        return str(meta.get("source") or "").strip().lower()
    return ""


def _element_time_ms(e: Dict[str, Any]) -> Optional[int]:
    meta = e.get("meta")
    if not isinstance(meta, dict):
        return None
    for k in ("start_ms", "time_ms", "end_ms"):
        try:
            v = meta.get(k)
            if v is not None:
                return int(v)
        except Exception:
            pass
    return None


def _query_focus_bonus(question: str, e: Dict[str, Any]) -> float:
    src = _element_source(e)
    q = str(question or "")
    bonus = 0.0
    if src == "video_transcript":
        bonus += 0.22
    elif src == "video_ocr":
        bonus -= 0.18
    text = str(e.get("text") or "")
    if src == "video_ocr" and _is_low_quality_video_ocr(text):
        bonus -= 1.0
    if re.search(r"视频|讲了什么|核心内容|关键信息|总结|概括", q):
        if src == "video_transcript":
            bonus += 0.12
        elif src == "video_ocr":
            bonus -= 0.12
    return bonus


def _pick_asset_for_element(
    *,
    page_assets: Dict[str, Dict[int, Dict[str, Any]]],
    timed_assets: Dict[str, List[Dict[str, Any]]],
    doc_id: str,
    page_idx: Optional[int],
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    if page_idx is not None:
        direct = (page_assets.get(doc_id) or {}).get(int(page_idx))
        if direct:
            return direct
    tm = None
    try:
        tm = int(meta.get("start_ms") if meta.get("start_ms") is not None else meta.get("time_ms"))
    except Exception:
        tm = None
    if tm is None:
        return {}
    candidates = timed_assets.get(doc_id) or []
    if not candidates:
        return {}
    best = min(candidates, key=lambda x: abs(int(x.get("time_ms") or 0) - tm))
    return best if best else {}

def query_elements(
    *,
    tenant_id: str,
    collection_id: str,
    doc_id: Optional[str],
    doc_ids: Optional[List[str]] = None,
    question: str,
    top_k: int = 8,
    retrieval_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    MVP query:
    - Prefer semantic retrieval via kb_embeddings (if available).
    - Fallback to keyword overlap on kb_elements.text.
    - Return items + lightweight citations (doc_id, page_idx, asset_path if available).
    """
    if not tenant_id:
        tenant_id = "default"
    if not collection_id:
        collection_id = "default"
    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()
    keywords = _extract_keywords(question)
    picked: List[Dict[str, Any]] = []
    retrieval_mode = "embedding"
    generation_mode = "fallback"
    doc_kind = ""
    doc_ids = [str(x).strip() for x in (doc_ids or []) if str(x).strip()]
    route = str((retrieval_policy or {}).get("route") or "").strip()
    if doc_id:
        try:
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT kind FROM documents WHERE tenant_id=? AND doc_id=? LIMIT 1",
                    (tenant_id, doc_id),
                ).fetchone()
            doc_kind = str((dict(row).get("kind") if row else "") or "").strip().lower() if row else ""
        except Exception:
            doc_kind = ""

    if doc_id and doc_kind == "video" and route == "video_fact_lookup":
        try:
            picked = _video_retrieval.build_video_transcript_facts(
                db=db,
                tenant_id=tenant_id,
                doc_id=doc_id,
                question=question,
                top_k=top_k,
            )
            if picked:
                retrieval_mode = "video_fact"
                generation_mode = "fallback"
            else:
                picked = []
        except Exception:
            picked = []

    if doc_id and doc_kind == "video" and not picked and (route == "video_window_query" or (not route and _video_retrieval.is_broad_video_question(question))):
        try:
            picked = _video_retrieval.build_video_transcript_windows(
                db=db,
                tenant_id=tenant_id,
                doc_id=doc_id,
                question=question,
                top_k=top_k,
            )
            if picked:
                retrieval_mode = "video_window"
                generation_mode = "fallback"
            else:
                picked = []
        except Exception:
            picked = []

    # 1) Semantic retrieval via embeddings
    qvec = embed_text(question)
    if not picked:
        try:
            emb_rows: List[Dict[str, Any]] = []
            if doc_id:
                emb_rows = db.list_embeddings_by_doc(tenant_id=tenant_id, doc_id=doc_id, embedding_type="text", limit=20000)
                # attach doc_id
                for r in emb_rows:
                    r["doc_id"] = doc_id
                    r["_doc_kind"] = doc_kind
            elif doc_ids:
                with db.connect() as conn:
                    placeholders = ",".join(["?"] * len(doc_ids))
                    rows = conn.execute(
                        f"""
                        SELECT b.element_id, b.doc_id, b.model, b.dim, b.vector_json, d.kind
                        FROM kb_embeddings b
                        JOIN documents d
                          ON d.tenant_id=b.tenant_id AND d.doc_id=b.doc_id
                        WHERE b.tenant_id=? AND b.doc_id IN ({placeholders}) AND b.embedding_type='text'
                        ORDER BY b.created_at ASC
                        LIMIT 20000
                        """,
                        (tenant_id, *doc_ids),
                    ).fetchall()
                emb_rows = []
                import json as _json

                for rr in rows:
                    d = dict(rr)
                    try:
                        d["vector"] = _json.loads(d.get("vector_json") or "[]")
                    except Exception:
                        d["vector"] = []
                    d.pop("vector_json", None)
                    d["_doc_kind"] = str(d.get("kind") or "").strip().lower()
                    emb_rows.append(d)
            else:
                # collection-level: join embeddings with documents by collection
                with db.connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT b.element_id, b.doc_id, b.model, b.dim, b.vector_json, d.kind
                        FROM kb_embeddings b
                        JOIN documents d
                          ON d.tenant_id=b.tenant_id AND d.doc_id=b.doc_id
                        WHERE b.tenant_id=? AND d.collection_id=? AND b.embedding_type='text'
                        ORDER BY b.created_at ASC
                        LIMIT 20000
                        """,
                        (tenant_id, collection_id),
                    ).fetchall()
                emb_rows = []
                import json as _json

                for rr in rows:
                    d = dict(rr)
                    try:
                        d["vector"] = _json.loads(d.get("vector_json") or "[]")
                    except Exception:
                        d["vector"] = []
                    d.pop("vector_json", None)
                    d["_doc_kind"] = str(d.get("kind") or "").strip().lower()
                    emb_rows.append(d)

            sims: List[Tuple[float, str, str]] = []  # sim, doc_id, element_id
            for r in emb_rows:
                vec = r.get("vector") or []
                sim = cosine_similarity(qvec, vec)
                if sim <= 0:
                    continue
                sims.append((sim, str(r.get("doc_id") or ""), str(r.get("element_id") or "")))
            sims.sort(key=lambda x: x[0], reverse=True)
            top = sims[: max(8, int(top_k) * 8)]
            eids = [eid for _, _, eid in top if eid]
            emap = db.get_elements_by_ids(tenant_id=tenant_id, element_ids=eids)
            reranked: List[Tuple[float, Dict[str, Any]]] = []
            for sim, did, eid in top:
                e = emap.get(eid)
                if not e:
                    continue
                e["doc_id"] = did or e.get("doc_id")
                e["_sim"] = float(sim)
                e["_doc_kind"] = doc_kind if doc_id else str(next((r.get("_doc_kind") for r in emb_rows if str(r.get("element_id") or "") == eid), "") or "")
                if _element_source(e) == "video_ocr" and _is_low_quality_video_ocr(str(e.get("text") or "")):
                    continue
                reranked.append((float(sim) + _query_focus_bonus(question, e), e))
            reranked.sort(key=lambda x: x[0], reverse=True)
            picked = [e for _, e in reranked[: max(1, int(top_k))]]
        except Exception:
            picked = []

    # 2) Fallback keyword retrieval
    if not picked:
        retrieval_mode = "keyword"
        # Load candidate text elements
        if doc_id:
            els = db.list_elements(tenant_id=tenant_id, doc_id=doc_id, limit=10000, offset=0)
        elif doc_ids:
            with db.connect() as conn:
                placeholders = ",".join(["?"] * len(doc_ids))
                rows = conn.execute(
                    f"""
                    SELECT e.element_id, e.doc_id, e.type, e.page_idx, e.text, e.meta_json, d.kind
                    FROM kb_elements e
                    JOIN documents d
                      ON d.tenant_id=e.tenant_id AND d.doc_id=e.doc_id
                    WHERE e.tenant_id=? AND e.doc_id IN ({placeholders}) AND e.type='text'
                    ORDER BY d.created_at DESC, e.page_idx ASC, e.created_at ASC
                    LIMIT 5000
                    """,
                    (tenant_id, *doc_ids),
                ).fetchall()
            els = [dict(r) for r in rows]
        else:
            # Collection-level: join documents to filter by collection.
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT e.element_id, e.doc_id, e.type, e.page_idx, e.text, e.meta_json, d.kind
                    FROM kb_elements e
                    JOIN documents d
                      ON d.tenant_id=e.tenant_id AND d.doc_id=e.doc_id
                    WHERE e.tenant_id=? AND d.collection_id=? AND e.type='text'
                    ORDER BY d.created_at DESC, e.page_idx ASC, e.created_at ASC
                    LIMIT 5000
                    """,
                    (tenant_id, collection_id),
                ).fetchall()
            els = [dict(r) for r in rows]

        scored: List[Tuple[int, Dict[str, Any]]] = []
        import json as _json
        for e in els:
            if not isinstance(e, dict):
                continue
            if str(e.get("type")) != "text":
                continue
            if not isinstance(e.get("meta"), dict):
                try:
                    e["meta"] = _json.loads(e.get("meta_json") or "{}")
                except Exception:
                    e["meta"] = {}
            e["_doc_kind"] = doc_kind if doc_id else str(e.get("kind") or "").strip().lower()
            text = str(e.get("text") or "")
            if _element_source(e) == "video_ocr" and _is_low_quality_video_ocr(text):
                continue
            score = _score_text(text, keywords)
            score = score + int(_query_focus_bonus(question, e) * 100)
            if score <= 0:
                continue
            scored.append((score, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        picked = [e for _, e in scored[: max(1, int(top_k))]]

    # Map page_idx -> asset_path if possible (page_image first, then frame_image for videos)
    citations = []
    # Build doc_id -> page_idx -> local_path mapping for picked docs only.
    doc_ids = []
    for e in picked:
        did = e.get("doc_id")
        if did and did not in doc_ids:
            doc_ids.append(str(did))
    page_map: Dict[str, Dict[int, Dict[str, Any]]] = {}
    timed_assets: Dict[str, List[Dict[str, Any]]] = {}
    if doc_ids:
        try:
            with db.connect() as conn:
                placeholders = ",".join(["?"] * len(doc_ids))
                rows = conn.execute(
                    f"""
                    SELECT doc_id, page_idx, kind, local_path, time_ms
                    FROM assets
                    WHERE tenant_id=? AND kind IN ('page_image','frame_image') AND doc_id IN ({placeholders})
                    """,
                    (tenant_id, *doc_ids),
                ).fetchall()
            for r in rows:
                did = str(r["doc_id"])
                if r["page_idx"] is None:
                    continue
                item = {
                    "asset_path": str(r["local_path"]),
                    "asset_kind": str(r["kind"] or ""),
                    "time_ms": r["time_ms"],
                }
                page_map.setdefault(did, {})[int(r["page_idx"])] = item
                timed_assets.setdefault(did, []).append(item)
        except Exception:
            page_map = {}
            timed_assets = {}

    items = []
    for e in picked:
        did = str(e.get("doc_id") or doc_id or "")
        page_idx = e.get("page_idx")
        full_text = str(e.get("text") or "").strip()
        snippet = full_text[:600]
        items.append(
            {
                "element_id": e.get("element_id"),
                "doc_id": did,
                "doc_kind": str(e.get("_doc_kind") or ""),
                "type": e.get("type"),
                "page_idx": page_idx,
                "snippet": snippet,
                "full_text": full_text[:20000],
                "score": e.get("_sim"),  # similarity (if embedding), else None
                "meta": e.get("meta") if isinstance(e.get("meta"), dict) else {},
            }
        )
        if did and page_idx is not None:
            meta = (e.get("meta") or {}) if isinstance(e.get("meta"), dict) else {}
            asset_info = _pick_asset_for_element(
                page_assets=page_map,
                timed_assets=timed_assets,
                doc_id=did,
                page_idx=int(page_idx),
                meta=meta,
            )
            citations.append(
                {
                    "doc_id": did,
                    "doc_kind": str(e.get("_doc_kind") or ""),
                    "page_idx": int(page_idx),
                    "asset_path": asset_info.get("asset_path"),
                    "asset_kind": asset_info.get("asset_kind"),
                    "time_ms": asset_info.get("time_ms"),
                    "start_ms": meta.get("start_ms"),
                    "end_ms": meta.get("end_ms"),
                    "source": meta.get("source"),
                }
            )

    answer = f"检索到与问题相关的内容片段 {len(items)} 条。"
    if keywords:
        answer += f" 关键词：{', '.join(keywords)}。"

    # Optional LLM answer generation over retrieved snippets.
    if items and llm_enabled():
        try:
            ctx_lines = []
            for i, it in enumerate(items[: max(1, int(top_k))], start=1):
                ctx_lines.append(
                    f"[{i}] doc={it.get('doc_id')} page={it.get('page_idx')} snippet={it.get('snippet')}"
                )
            system_prompt = (
                "你是文档问答助手。请仅基于给定片段回答，不要编造。"
                "若信息不足，请明确说信息不足。输出纯文本答案。"
            )
            user_prompt = (
                f"问题：{question}\n\n"
                f"候选片段：\n" + "\n".join(ctx_lines)
            )
            llm_ans = chat_complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.1, max_tokens=700)
            if llm_ans:
                answer = llm_ans
                generation_mode = "llm"
        except Exception:
            pass

    return {
        "tenant_id": tenant_id,
        "collection_id": collection_id,
        "doc_id": doc_id,
        "doc_ids": doc_ids,
        "mode": f"{retrieval_mode}+{generation_mode}",
        "retrieval_mode": retrieval_mode,
        "generation_mode": generation_mode,
        "answer": answer,
        "items": items,
        "citations": citations,
    }
