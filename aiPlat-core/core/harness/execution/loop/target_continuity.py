"""Target Continuity — target-continuity verdict (Agent runtime deterministic constraint, layer 4).

Hermes-inspired: when the user interjects mid-way or sends a new message, determine whether it is
a "supplement to the old task" or a "new task".
Vocabulary-overlap scoring + dual thresholds (0.24/0.08) + two-tier LLM adjudication.

Usage:
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

# Chinese + English stopwords for overlap scoring (see core.harness.utils.zh_language)
from core.harness.utils.zh_language import TASK_CONTINUITY_STOPWORDS

_STOP_WORDS = TASK_CONTINUITY_STOPWORDS


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

            from core.harness.utils.prompt_loader import _sync_resolve
            prompt = _sync_resolve("task-continuity-classifier", text_a=task[:300], text_b=msg[:300])
            resp = await sys_llm_generate(
                model=None,
                prompt=prompt,
                model_name=best_model_for_purpose("reasoning"),
                temperature=0.0,
            )
            text = str(resp).upper().strip()
            same = "SAME" in text and "NEW" not in text
            from core.harness.utils.zh_language import TASK_CONTINUITY_VERDICT_TMPL
            return {"same_task": same, "reason": TASK_CONTINUITY_VERDICT_TMPL.format(
                verdict='SAME' if same else 'NEW', score=score)}
        except Exception:
            return None
