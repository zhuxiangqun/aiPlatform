"""Target Continuity — 目标连续性裁决 (Agent 运行时确定性约束第4层).

Hermes-inspired: 用户中途插话/新消息时, 判定是"补充旧任务"还是"新任务"。
词汇重叠度评分 + 双阈值 (0.24/0.08) + LLM 两级裁决。

用法:
  judge = TargetContinuity()
  verdict = judge.decide(current_task, new_input)
  # → {"same_task": bool, "overlap_score": float, "method": "fast"|"llm"}
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

log = logging.getLogger("aiplat.continuity")

# Chinese + English stopwords for overlap scoring
_STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "and", "but", "or", "nor", "not", "so",
    "yet", "both", "either", "neither", "each", "every", "all", "any",
    "few", "more", "most", "other", "some", "such", "no", "only", "own",
    "same", "than", "too", "very", "just", "because", "about", "over",
    "this", "that", "these", "those", "it", "its", "he", "she", "they",
    "we", "you", "me", "him", "her", "us", "them", "my", "your", "his",
}


def _tokenize(text: str) -> set:
    """Extract significant tokens from text (removes stopwords + short tokens)."""
    tokens = set()
    # Split Chinese by character n-grams; English by word boundaries
    # Chinese: extract 2-char bigrams as tokens
    chinese_chars = "".join(c for c in text if "\u4e00" <= c <= "\u9fff")
    for i in range(len(chinese_chars) - 1):
        bigram = chinese_chars[i : i + 2]
        if bigram not in _STOP_WORDS:
            tokens.add(bigram)
    # English: extract words >= 3 chars
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    for w in words:
        if w not in _STOP_WORDS:
            tokens.add(w)
    return tokens


def _overlap_score(t1: str, t2: str) -> float:
    """Compute token overlap score between two texts. Range [0, 1]."""
    s1, s2 = _tokenize(t1), _tokenize(t2)
    if not s1 and not s2:
        return 0.0
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)  # Jaccard


class TargetContinuity:
    """Two-tier task continuity verdict (fast overlap + LLM fallback).

    Thresholds (from Hermes, validated on real conversation data):
      - overlap >= 0.24 → SAME task (fast path)
      - overlap <= 0.08 → NEW task (fast path)
      - 0.08 < overlap < 0.24 → LLM two-level adjudication
    """

    def __init__(self, high: float = 0.24, low: float = 0.08):
        self._high = high
        self._low = low
        self._llm_count = 0

    def decide(self, current_task: str, new_input: str) -> Dict[str, Any]:
        """Return {same_task, overlap_score, method, reason}."""
        score = _overlap_score(current_task, new_input)

        if score >= self._high:
            return {
                "same_task": True, "overlap_score": round(score, 4),
                "method": "fast", "reason": f"高重叠 ({score:.3f} >= {self._high})",
            }
        if score <= self._low:
            return {
                "same_task": False, "overlap_score": round(score, 4),
                "method": "fast", "reason": f"低重叠 ({score:.3f} <= {self._low})",
            }

        # Ambiguous zone — heuristic conservative fallback (LLM path requires async)
        self._llm_count += 1
        return {
            "same_task": True, "overlap_score": round(score, 4),
            "method": "heuristic", "reason": f"模糊区保守(重叠={score:.3f}): 默认same_task",
        }

    async def _llm_decide(self, task: str, msg: str, score: float) -> Optional[Dict[str, Any]]:
        """Async LLM call to decide if two texts are about the same task."""
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate

            prompt = (
                "You are a task continuity classifier. Given two texts, decide if they "
                "are about the SAME task or different tasks. Respond with ONLY 'SAME' or 'NEW'.\n\n"
                f"Current task: {task[:300]}\n\n"
                f"New input: {msg[:300]}\n\n"
                "Are these about the SAME task or a NEW task?"
            )
            resp = await sys_llm_generate(
                model=None,
                prompt=prompt,
                model_name=best_model_for_purpose("reasoning"),
                temperature=0.0,
            )
            text = str(resp).upper().strip()
            same = "SAME" in text and "NEW" not in text
            return {"same_task": same, "reason": f"LLM裁决: {'SAME' if same else 'NEW'} (重叠={score:.3f})"}
        except Exception:
            return None
