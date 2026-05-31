from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .embeddings import cosine_similarity, embed_text
from core.api.facades.kb_facade import kb_extract_keywords as extract_keywords
from core.api.facades.kb_facade import kb_score_text as score_text
from core.api.facades.kb_facade import kb_element_source as element_source


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
    question: str,
    segments: List[Dict[str, Any]],
    window_size_ms: int = 60000,
    step_ms: int = 30000,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    if not segments:
        return []

    qvec = embed_text(question)
    keywords = extract_keywords(question)

    max_ms = max(int(s.get("end_ms") or s.get("start_ms") or 0) for s in segments)
    windows: List[Tuple[float, int, int, str]] = []

    for start_ms in range(0, max_ms + 1, step_ms):
        end_ms = start_ms + window_size_ms
        window_texts: List[str] = []
        window_start = None
        window_end = None
        for s in segments:
            s_start = int(s.get("start_ms") or 0)
            s_end = int(s.get("end_ms") or 0)
            if s_end > start_ms and s_start < end_ms:
                txt = str(s.get("text") or "").strip()
                if txt:
                    window_texts.append(txt)
                    if window_start is None or s_start < window_start:
                        window_start = s_start
                    if window_end is None or s_end > window_end:
                        window_end = s_end
        if not window_texts:
            continue
        combined = " ".join(window_texts[:20])
        sim = cosine_similarity(qvec, embed_text(combined[:4000]))
        kw_score = score_text(combined, keywords)
        total_score = sim + kw_score * 0.01
        windows.append((total_score, window_start or start_ms, window_end or end_ms, combined[:2000]))

    windows.sort(key=lambda x: -x[0])
    return [
        {"score": round(sc, 4), "start_ms": st, "end_ms": en, "text": tx}
        for sc, st, en, tx in windows[:top_k]
    ]


def build_video_transcript_facts(
    question: str,
    segments: List[Dict[str, Any]],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    if not segments:
        return []

    qvec = embed_text(question)
    keywords = extract_keywords(question)
    scored: List[Tuple[float, Dict[str, Any]]] = []

    for s in segments:
        txt = str(s.get("text") or "").strip()
        if not txt:
            continue
        sim = cosine_similarity(qvec, embed_text(txt[:2000]))
        kw_score = score_text(txt, keywords)
        total_score = sim + kw_score * 0.01
        scored.append((total_score, s))

    scored.sort(key=lambda x: -x[0])
    return [
        {
            "score": round(sc, 4),
            "start_ms": int(s.get("start_ms") or 0),
            "end_ms": int(s.get("end_ms") or 0),
            "text": str(s.get("text") or "").strip(),
        }
        for sc, s in scored[:top_k]
    ]