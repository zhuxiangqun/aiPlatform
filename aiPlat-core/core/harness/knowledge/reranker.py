"""
Cross-Encoder Reranker — lightweight BM25-based re-ranking of retrieval results.

Design principle (RAG article §02):
  Coarse retrieval returns 20-30 chunks. Sending all to the LLM wastes tokens
  and introduces noise. A lightweight re-ranker selects the top 3-5 most relevant
  chunks based on query-chunk relevance scoring.

Implementation: BM25 scoring (no external model dependency needed).
"""

from __future__ import annotations

import re
from collections import Counter
from math import log
from typing import Any, List, Tuple


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r'[\u4e00-\u9fff\uff00-\uffef]|[a-zA-Z0-9_]+', str(text).lower())
    cjk = re.findall(r'[\u4e00-\u9fff\uff00-\uffef]', str(text))
    return tokens + cjk


def rerank_by_relevance(query: str, chunks: List[str], top_k: int = 5) -> List[Tuple[int, float]]:
    if not chunks:
        return []
    # BM25 scoring
    K1, B = 1.5, 0.75
    doc_lens = [len(_tokenize(c)) for c in chunks]
    avgdl = sum(doc_lens) / max(len(chunks), 1)
    df: dict = {}
    for chunk in chunks:
        for token in set(_tokenize(chunk)):
            df[token] = df.get(token, 0) + 1
    N = len(chunks)
    scored = []
    qtokens = _tokenize(query)
    for idx, chunk in enumerate(chunks):
        doc_tokens = _tokenize(chunk)
        tf = Counter(doc_tokens)
        dl = doc_lens[idx]
        score = 0.0
        for qt in qtokens:
            n = df.get(qt, 0)
            if n == 0:
                continue
            f = tf.get(qt, 0)
            idf = log((N - n + 0.5) / (n + 0.5) + 1.0)
            score += idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / max(avgdl, 1)))
        scored.append((idx, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def rerank_by_multi_factor(query: str, candidates: List[str], top_k: int = 8) -> List[Tuple[int, float]]:
    """Multi-factor re-rank ported from syscalls/retrieval.py:_rerank().

    Scores each candidate by:
    - Token overlap density (0.6 weight): how many query tokens appear
    - First-match position bonus (0.1): earlier match → higher score
    - Exact phrase bonus (0.2): contiguous query substrings in candidate
    - Length fitness (0.1): prefers concise passages (50-500 chars optimal)

    Zero-model, zero-API, < 1ms for typical top_n.
    """
    if not candidates:
        return []

    q_lower = query.lower()
    q_tokens = re.findall(r'[\u4e00-\u9fff]{2,4}|[a-zA-Z]{2,}', q_lower)
    q_phrases = [p for p in re.findall(r'[\u4e00-\u9fff]{3,6}|[a-zA-Z]{4,}', q_lower) if len(p) >= 3]

    if not q_tokens:
        return [(i, 0.0) for i in range(min(top_k, len(candidates)))]

    scored: list = []
    for idx, text_raw in enumerate(candidates):
        text = str(text_raw).lower()
        if not text:
            scored.append((idx, 0.0))
            continue

        match_count = sum(1 for t in q_tokens if t in text)
        overlap_score = match_count / max(1, len(q_tokens))

        first_pos = len(text)
        for t in q_tokens:
            pos = text.find(t)
            if pos >= 0 and pos < first_pos:
                first_pos = pos
        pos_bonus = max(0, 0.1 - 0.1 * (first_pos / max(1, len(text)))) if first_pos < len(text) else 0.0

        phrase_bonus = 0.0
        for phrase in q_phrases:
            if phrase in text:
                phrase_bonus += 0.15

        text_len = len(text)
        if text_len < 30:       len_score = -0.05
        elif text_len < 500:    len_score = 0.05
        elif text_len < 2000:   len_score = 0.0
        else:                   len_score = -0.1

        final = overlap_score * 0.6 + pos_bonus * 0.1 + phrase_bonus * 0.2 + len_score * 0.1
        scored.append((idx, final))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
