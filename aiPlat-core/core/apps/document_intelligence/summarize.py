from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from core.apps.document_intelligence.llm import chat_complete, extract_json_block, llm_enabled
from core.apps.document_intelligence.query import _extract_keywords, _score_text
from core.apps.multimodal_kb.db import KBSqlite
from core.apps.multimodal_kb.storage import get_tenant_storage


def _split_sentences(text: str) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    # split by newline and sentence delimiters
    parts = re.split(r"[\n。！？.!?]+", t)
    out = []
    for p in parts:
        p = p.strip()
        if len(p) >= 6:
            out.append(p)
    return out


def summarize_document(
    *,
    tenant_id: str,
    collection_id: str,
    doc_id: str,
    profile: str = "key_points",
    max_points: int = 10,
) -> Dict[str, Any]:
    """
    MVP summarization (no LLM):
    - Select top sentences from kb_elements.text by a simple heuristic.
    - Always provide citations (page_idx + page_image asset_path).
    Later: replace with LLM summarizer with citations.
    """
    if not tenant_id:
        tenant_id = "default"
    if not collection_id:
        collection_id = "default"
    if not doc_id:
        raise ValueError("doc_id_required")

    st = get_tenant_storage(tenant_id)
    db = KBSqlite(st.db_path)
    db.ensure_schema()

    els = db.list_elements(tenant_id=tenant_id, doc_id=doc_id, type="text", limit=10000, offset=0)
    retrieval_mode = "rule"
    generation_mode = "fallback"

    # Build a pseudo query based on profile (heuristic keywords)
    profile = (profile or "key_points").strip().lower()
    seed_q = {
        "key_points": "核心 要点 总结 结论",
        "outline": "目录 章节 概述",
        "actions": "行动 建议 计划 下一步",
        "risks": "风险 问题 隐患",
    }.get(profile, "核心 要点 总结")
    keywords = _extract_keywords(seed_q)

    # Collect candidate sentences with page info
    candidates: List[Tuple[int, int, str]] = []  # score, page_idx, sentence
    for e in els:
        page_idx = int(e.get("page_idx") or 0)
        text = str(e.get("text") or "")
        # Prefer earlier pages for outline, later pages for actions/risks (tiny heuristic)
        bias = 0
        if profile == "outline":
            bias = max(0, 5 - page_idx)
        elif profile in ("actions", "risks"):
            bias = min(5, page_idx)
        for s in _split_sentences(text):
            # If the document is very short / not matching our Chinese seed keywords (e.g. fixture PDF),
            # fall back to a length-based baseline score so we still produce points.
            kw_sc = _score_text(s, keywords)
            base_sc = min(5, max(0, len(s) // 8))  # 8 chars ~ 1 point
            sc = kw_sc + base_sc + bias
            if sc <= 0:
                continue
            candidates.append((sc, page_idx, s))

    candidates.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate by sentence text
    picked: List[Tuple[int, int, str]] = []
    seen = set()
    for sc, pg, s in candidates:
        key = s[:120]
        if key in seen:
            continue
        picked.append((sc, pg, s))
        seen.add(key)
        if len(picked) >= max(1, int(max_points)):
            break

    # page image mapping for citations
    citations = []
    try:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT page_idx, local_path FROM assets WHERE tenant_id=? AND doc_id=? AND kind='page_image'",
                (tenant_id, doc_id),
            ).fetchall()
        page_map = {int(r["page_idx"]): str(r["local_path"]) for r in rows if r["page_idx"] is not None}
    except Exception:
        page_map = {}

    points = []
    for idx, (_, pg, s) in enumerate(picked, start=1):
        points.append(
            {
                "idx": idx,
                "text": s,
                "page_idx": int(pg),
            }
        )
        citations.append({"doc_id": doc_id, "page_idx": int(pg), "asset_path": page_map.get(int(pg))})

    summary = f"已生成 {len(points)} 条{profile}要点（MVP 规则版）。"

    # 可选：LLM 根据候选句生成更自然的总结，但保留引用页码。
    if points and llm_enabled():
        try:
            ctx_lines = []
            for p in points[: max(1, int(max_points))]:
                ctx_lines.append(f"[{p['idx']}] page={p['page_idx']} text={p['text']}")
            system_prompt = (
                "你是文档总结助手。请仅基于提供的候选句生成总结。"
                "输出 JSON：{\"summary\": string, \"points\": [{\"idx\": number, \"text\": string, \"page_idx\": number}] }。"
                "points 数量不要超过输入候选数，不要编造新的页码。"
            )
            user_prompt = (
                f"profile={profile}\n"
                f"max_points={max_points}\n"
                "候选句：\n" + "\n".join(ctx_lines)
            )
            llm_raw = chat_complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2, max_tokens=900)
            obj = extract_json_block(llm_raw or "")
            if isinstance(obj, dict):
                llm_summary = str(obj.get("summary") or "").strip()
                llm_points = obj.get("points") or []
                normalized = []
                allowed_pages = {int(p["page_idx"]): True for p in points}
                for idx, p in enumerate(llm_points, start=1):
                    if not isinstance(p, dict):
                        continue
                    txt = str(p.get("text") or "").strip()
                    try:
                        pg = int(p.get("page_idx"))
                    except Exception:
                        continue
                    if not txt or pg not in allowed_pages:
                        continue
                    normalized.append({"idx": idx, "text": txt, "page_idx": pg})
                    if len(normalized) >= max(1, int(max_points)):
                        break
                if normalized:
                    points = normalized
                    citations = [
                        {"doc_id": doc_id, "page_idx": int(p["page_idx"]), "asset_path": page_map.get(int(p["page_idx"]))}
                        for p in points
                    ]
                    if llm_summary:
                        summary = llm_summary
                    else:
                        summary = f"已生成 {len(points)} 条{profile}要点。"
                    generation_mode = "llm"
        except Exception:
            pass

    return {
        "tenant_id": tenant_id,
        "collection_id": collection_id,
        "doc_id": doc_id,
        "profile": profile,
        "mode": f"{retrieval_mode}+{generation_mode}",
        "retrieval_mode": retrieval_mode,
        "generation_mode": generation_mode,
        "summary": summary,
        "points": points,
        "citations": citations,
    }
