from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from . import video_retrieval as _video_retrieval
from core.api.core_facade import kb_extract_keywords, kb_llm_chat_complete as chat_complete, kb_llm_enabled as llm_enabled, kb_get_tenant_storage as get_tenant_storage


def _get_keywords(text: str) -> List[str]:
    try:
        return kb_extract_keywords(text)
    except Exception:
        return re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{2,}', str(text).lower())


async def query_elements(
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
    db = get_knowledge_db()
    db.ensure_schema()
    keywords = _get_keywords(question)
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

    from core.api.core_facade import kb_retrieve
    import json as _json

    picked: List[Dict[str, Any]] = []
    try:
        kb_results = kb_retrieve(query=question, doc_ids=doc_ids or [], tenant_id=tenant_id, collection_id=collection_id, top_k=max(8, int(top_k) * 2))
        for r in kb_results:
            r["_doc_kind"] = doc_kind
        picked = kb_results[: max(1, int(top_k))]
        retrieval_mode = "hybrid_unified"
    except Exception:
        picked = []

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
            llm_ans = await chat_complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.1, max_tokens=700)
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


def _pick_asset_for_element(
    *,
    page_assets: dict,
    timed_assets: dict,
    doc_id: str,
    page_idx: int,
    meta: dict,
) -> dict:
    asset = (page_assets.get(doc_id, {}) or {}).get(page_idx, {})
    if asset:
        return asset
    timed = timed_assets.get(doc_id, [])
    if timed:
        return timed[0]
    return {}
