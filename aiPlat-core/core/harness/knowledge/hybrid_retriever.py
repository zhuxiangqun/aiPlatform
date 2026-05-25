"""
Hybrid Retriever — BM25 keyword + vector semantic fusion via RRF (Reciprocal Rank Fusion).

Design principle (RAG article §02-04):
  Pure vector retrieval misses exact matches (SKU codes, contract numbers, IDs).
  BM25 keyword retrieval misses semantic equivalents ("西红柿" vs "番茄").
  RRF merges both result lists so documents ranked high in EITHER approach
  float to the top, while documents ranked low in both sink.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Tuple


class BM25Scorer:
    _K1 = 1.5
    _B = 0.75

    def __init__(self, corpus: List[str]):
        self._doc_count = len(corpus)
        self._avgdl = sum(len(d.split()) for d in corpus) / max(self._doc_count, 1)
        self._df: Dict[str, int] = {}
        for doc in corpus:
            for token in set(self._tokenize(doc)):
                self._df[token] = self._df.get(token, 0) + 1

    def score(self, query: str, doc: str) -> float:
        tokens = self._tokenize(doc)
        dl = len(tokens)
        tf = Counter(tokens)
        score = 0.0
        for qt in self._tokenize(query):
            n = self._df.get(qt, 0)
            if n == 0:
                continue
            f = tf.get(qt, 0)
            idf = math.log((self._doc_count - n + 0.5) / (n + 0.5) + 1.0)
            score += idf * (f * (self._K1 + 1)) / (f + self._K1 * (1 - self._B + self._B * dl / max(self._avgdl, 1)))
        return score

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        tokens = re.findall(r'[\u4e00-\u9fff\uff00-\uffef]|[a-zA-Z0-9_]+', text.lower())
        # Also keep multi-char CJK as individual tokens
        cjk = re.findall(r'[\u4e00-\u9fff\uff00-\uffef]', text)
        return tokens + cjk


def rrf_fusion(
    vec_ranked: List[Tuple[int, Any]],
    kw_ranked: List[Tuple[int, Any]],
    k: int = 60,
    top_n: int = 10,
) -> List[Any]:
    scores: Dict[int, float] = {}
    items: Dict[int, Any] = {}
    for rank, (idx, item) in enumerate(vec_ranked):
        scores[idx] = scores.get(idx, 0) + 1.0 / (k + rank + 1)
        items[idx] = item
    for rank, (idx, item) in enumerate(kw_ranked):
        scores[idx] = scores.get(idx, 0) + 1.0 / (k + rank + 1)
        items[idx] = item
    ranked = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)
    return [items[i] for i in ranked[:top_n]]


def keyword_search(query: str, chunks: List[str], top_k: int = 20) -> List[Tuple[int, float]]:
    bm25 = BM25Scorer(chunks)
    scored = [(i, bm25.score(query, chunk)) for i, chunk in enumerate(chunks)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [(i, s) for i, s in scored[:top_k] if s > 0]
