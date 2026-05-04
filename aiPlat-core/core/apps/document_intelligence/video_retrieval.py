from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from core.apps.document_intelligence.embeddings import cosine_similarity, embed_text
from core.apps.multimodal_kb.db import KBSqlite


def extract_keywords(q: str) -> List[str]:
    q = (q or "").strip()
    if not q:
        return []
    toks: List[str] = []
    toks += re.findall(r"[A-Za-z0-9_]{2,}", q)
    toks += re.findall(r"[\u4e00-\u9fff]{2,}", q)
    seen = set()
    out: List[str] = []
    for t in toks:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out[:20]


def score_text(text: str, keywords: List[str]) -> int:
    if not text or not keywords:
        return 0
    t = text.lower()
    s = 0
    for k in keywords:
        kk = k.lower()
        s += t.count(kk) * max(1, len(kk) // 2)
    return s


def element_source(e: Dict[str, Any]) -> str:
    meta = e.get("meta")
    if isinstance(meta, dict):
        return str(meta.get("source") or "").strip().lower()
    return ""


def element_time_ms(e: Dict[str, Any]) -> Optional[int]:
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


def is_broad_video_question(question: str) -> bool:
    q = str(question or "").strip()
    return bool(re.search(r"视频|资料|主要讲了什么|讲了什么|核心内容|关键信息|重点|总结|概括|梳理", q))


def build_video_transcript_windows(
    *,
    db: KBSqlite,
    tenant_id: str,
    doc_id: str,
    question: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    els = db.list_elements(tenant_id=tenant_id, doc_id=doc_id, limit=10000, offset=0)
    transcript: List[Dict[str, Any]] = []
    for e in els:
        if not isinstance(e, dict):
            continue
        if str(e.get("type")) != "text":
            continue
        if element_source(e) != "video_transcript":
            continue
        text = str(e.get("text") or "").strip()
        if len(text) < 6:
            continue
        meta = e.get("meta") if isinstance(e.get("meta"), dict) else {}
        start_ms = element_time_ms(e)
        if start_ms is None:
            continue
        end_ms = meta.get("end_ms")
        try:
            end_ms = int(end_ms) if end_ms is not None else int(start_ms)
        except Exception:
            end_ms = int(start_ms)
        transcript.append(
            {
                "element_id": e.get("element_id"),
                "page_idx": e.get("page_idx"),
                "text": text,
                "start_ms": int(start_ms),
                "end_ms": int(end_ms),
            }
        )
    if not transcript:
        return []
    transcript.sort(key=lambda x: (int(x.get("start_ms") or 0), int(x.get("page_idx") or 0)))
    window_ms = 60000
    step_ms = 30000
    start0 = int(transcript[0]["start_ms"])
    endN = int(max(x["end_ms"] for x in transcript))
    windows: List[Tuple[int, int, str, List[Dict[str, Any]]]] = []
    t = start0
    while t <= endN:
        t_end = t + window_ms
        segs = [x for x in transcript if not (int(x["end_ms"]) < t or int(x["start_ms"]) > t_end)]
        if segs:
            merged = " ".join(str(x.get("text") or "").strip() for x in segs).strip()
            if merged:
                windows.append((t, t_end, merged, segs))
        t += step_ms
    if not windows:
        return []
    qvec = embed_text(question)
    kws = extract_keywords(question)
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for st, ed, text, segs in windows:
        sim = cosine_similarity(qvec, embed_text(text[:4000]))
        kw = score_text(text, kws)
        score = float(sim) + min(0.30, kw / 100.0)
        center = segs[len(segs) // 2]
        scored.append(
            (
                score,
                {
                    "element_id": center.get("element_id"),
                    "doc_id": doc_id,
                    "_doc_kind": "video",
                    "_sim": float(score),
                    "type": "text",
                    "page_idx": center.get("page_idx"),
                    "text": text[:6000],
                    "meta": {
                        "source": "video_transcript_window",
                        "time_ms": int(st),
                        "start_ms": int(st),
                        "end_ms": int(ed),
                        "window_size_ms": window_ms,
                        "segment_count": len(segs),
                    },
                },
            )
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[: max(1, min(int(top_k), 4))]]


def build_video_transcript_facts(
    *,
    db: KBSqlite,
    tenant_id: str,
    doc_id: str,
    question: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    els = db.list_elements(tenant_id=tenant_id, doc_id=doc_id, limit=10000, offset=0)
    transcript: List[Dict[str, Any]] = []
    for e in els:
        if not isinstance(e, dict):
            continue
        if str(e.get("type")) != "text":
            continue
        if element_source(e) != "video_transcript":
            continue
        text = str(e.get("text") or "").strip()
        if len(text) < 2:
            continue
        meta = e.get("meta") if isinstance(e.get("meta"), dict) else {}
        start_ms = element_time_ms(e)
        if start_ms is None:
            continue
        end_ms = meta.get("end_ms")
        try:
            end_ms = int(end_ms) if end_ms is not None else int(start_ms)
        except Exception:
            end_ms = int(start_ms)
        transcript.append(
            {
                "element_id": e.get("element_id"),
                "page_idx": e.get("page_idx"),
                "text": text,
                "start_ms": int(start_ms),
                "end_ms": int(end_ms),
            }
        )
    if not transcript:
        return []
    transcript.sort(key=lambda x: (int(x.get("start_ms") or 0), int(x.get("page_idx") or 0)))
    qvec = embed_text(question)
    keywords = extract_keywords(question)
    wants_precise_fact = bool(re.search(r"谁|叫什么|名字|姓名|哪一年|什么时候|哪个公司|哪个学校|多少|数字|哪一句|哪段", str(question or "")))
    scored: List[Tuple[float, int]] = []
    for idx, seg in enumerate(transcript):
        text = str(seg.get("text") or "").strip()
        sim = cosine_similarity(qvec, embed_text(text[:2000]))
        kw_score = score_text(text, keywords)
        bonus = 0.18
        if wants_precise_fact and re.search(r"我叫|我是|叫做|名字|称为|来自|担任|主持人|嘉宾|老师|博士|总|先生|女士", text):
            bonus += 0.22
        if len(text) <= 64:
            bonus += 0.04
        score = float(sim) + min(0.35, kw_score / 80.0) + bonus
        scored.append((score, idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen: List[Dict[str, Any]] = []
    seen = set()
    score_map = {i: s for s, i in scored}
    for _, idx in scored[: max(1, min(int(top_k) * 3, 24))]:
        center = transcript[idx]
        sig = (int(center.get("start_ms") or 0) // 1000, int(center.get("end_ms") or 0) // 1000)
        if sig in seen:
            continue
        seen.add(sig)
        left = max(0, idx - 1)
        right = min(len(transcript) - 1, idx + 1)
        segs = transcript[left : right + 1]
        merged_text = " ".join(str(s.get("text") or "").strip() for s in segs).strip()
        chosen.append(
            {
                "element_id": center.get("element_id"),
                "doc_id": doc_id,
                "_doc_kind": "video",
                "_sim": float(score_map.get(idx, 0.0)),
                "type": "text",
                "page_idx": center.get("page_idx"),
                "text": merged_text[:6000],
                "meta": {
                    "source": "video_transcript_fact",
                    "time_ms": int(center.get("start_ms") or 0),
                    "start_ms": int(segs[0].get("start_ms") or 0),
                    "end_ms": int(segs[-1].get("end_ms") or 0),
                    "segment_count": len(segs),
                    "focus": "fine_grained_fact_lookup",
                },
            }
        )
        if len(chosen) >= max(1, min(int(top_k), 8)):
            break
    return chosen
