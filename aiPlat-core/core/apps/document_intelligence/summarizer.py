"""Document summarization — MVP rule-based + optional LLM summarizer.

Caller: aiPlat-platform/kb/intelligence/summarize.py (re-export stub)
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from core.apps.document_intelligence.llm_client import chat_complete, extract_json_block, llm_enabled
from core.harness.knowledge.utils import extract_keywords, score_text
from core.apps.document_intelligence.kb_provider import get_tenant_storage


def _split_sentences(text: str) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"[\n。！？.!?]+", t)
    out = []
    for p in parts:
        p = p.strip()
        if len(p) >= 6:
            out.append(p)
    return out


async def summarize_document(
    *,
    tenant_id: str,
    collection_id: str,
    doc_id: str,
    profile: str = "key_points",
    max_points: int = 10,
) -> Dict[str, Any]:
    """Summarize a document by selecting top sentences from kb_elements.

    Rule-based MVP with optional LLM refinement.
    Always provides citations (page_idx + page_image asset_path).
    """
    if not tenant_id:
        tenant_id = "default"
    if not collection_id:
        collection_id = "default"
    if not doc_id:
        raise ValueError("doc_id_required")

    st = get_tenant_storage(tenant_id)
    from core.harness.infrastructure.infra_bridge import create_infra_database_client
    import os as _os
    from pathlib import Path as _Path
    _aiplat_home = _os.getenv("AIPLAT_HOME", str(_Path.home() / ".aiplat"))
    _db_path = str(_Path(_aiplat_home).expanduser() / "kb" / "tenants" / (tenant_id or "default") / "kb.sqlite3")
    conn = create_infra_database_client(_db_path)
    try:
        conn.row_factory = None
        cols = conn.execute("PRAGMA table_info(kb_elements)").fetchall()
        col_names = [c[1] for c in cols]
        rows = conn.execute(
            "SELECT * FROM kb_elements WHERE tenant_id=? AND doc_id=? AND type=? ORDER BY page_idx ASC, created_at ASC LIMIT ? OFFSET ?",
            (tenant_id, doc_id, "text", 10000, 0),
        ).fetchall()
        els = []
        for r in rows:
            d = {}
            for i, name in enumerate(col_names):
                v = r[i]
                if name in ("bbox_json", "cells_json", "meta_json"):
                    try:
                        d[name.replace("_json", "")] = json.loads(v or "{}")
                    except Exception:
                        d[name.replace("_json", "")] = {}
                else:
                    d[name] = v
            els.append(d)
    finally:
        conn.close()

    retrieval_mode = "rule"
    generation_mode = "fallback"

    profile = (profile or "key_points").strip().lower()
    seed_q = {
        "key_points": "核心 要点 总结 结论",
        "outline": "目录 章节 概述",
        "actions": "行动 建议 计划 下一步",
        "risks": "风险 问题 隐患",
    }.get(profile, "核心 要点 总结")
    keywords = extract_keywords(seed_q)

    candidates: List[Tuple[int, int, str]] = []
    for e in els:
        page_idx = int(e.get("page_idx") or 0)
        text = str(e.get("text") or "")
        bias = 0
        if profile == "outline":
            bias = max(0, 5 - page_idx)
        elif profile in ("actions", "risks"):
            bias = min(5, page_idx)
        for s in _split_sentences(text):
            kw_sc = score_text(s, keywords)
            base_sc = min(5, max(0, len(s) // 8))
            sc = kw_sc + base_sc + bias
            if sc <= 0:
                continue
            candidates.append((sc, page_idx, s))

    if not candidates:
        # Fallback: no keyword match — pick longest sentences as summary
        all_sents: List[Tuple[int, int, str]] = []
        for e in els:
            page_idx = int(e.get("page_idx") or 0)
            text = str(e.get("text") or "")
            for s in _split_sentences(text):
                all_sents.append((len(s), page_idx, s))
        all_sents.sort(key=lambda x: x[0], reverse=True)
        candidates = [(sc, pg, s) for sc, pg, s in all_sents[:max(1, int(max_points))]]

    candidates.sort(key=lambda x: x[0], reverse=True)

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

    citations = []
    try:
        aconn = _mk_conn(_db_path)
        try:
            rows = aconn.execute(
                "SELECT page_idx, local_path FROM assets WHERE tenant_id=? AND doc_id=? AND kind='page_image'",
                (tenant_id, doc_id),
            ).fetchall()
            page_map = {int(r["page_idx"]): str(r["local_path"]) for r in rows if r["page_idx"] is not None}
        finally:
            aconn.close()
    except Exception:
        page_map = {}

    points = []
    for idx, (_, pg, s) in enumerate(picked, start=1):
        points.append({"idx": idx, "text": s, "page_idx": int(pg)})
        citations.append({"doc_id": doc_id, "page_idx": int(pg), "asset_path": page_map.get(int(pg))})

    summary = f"已生成 {len(points)} 条{profile}要点。"

    if points and llm_enabled():
        try:
            ctx_lines = []
            for p in points[: max(1, int(max_points))]:
                ctx_lines.append(f"[{p['idx']}] page={p['page_idx']} text={p['text']}")
            from core.harness.utils.prompt_loader import _sync_resolve
            system_prompt = _sync_resolve("doc-summarizer", sentences="")
            # Strip the ${sentences} part from the template since we pass sentences via user_prompt
            system_prompt = system_prompt.split("\n\n候选句：")[0]
            user_prompt = (
                f"profile={profile}\n"
                f"max_points={max_points}\n"
                "候选句：\n" + "\n".join(ctx_lines)
            )
            llm_raw = await chat_complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.2, max_tokens=900)
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
                    summary = llm_summary if llm_summary else f"已生成 {len(points)} 条{profile}要点。"
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
