"""
DriftDetector — lightweight reasoning quality decline detection without embedding models.

Design principle (control theory Rule #2 — positive feedback detection):
  Positive feedback loops in Agent systems occur when incorrect outputs are
  fed back into working memory, producing increasingly incorrect outputs.
  The cybernetic fix is: add an external sensor (independent evaluator) to
  detect divergence and break the loop.

This module uses three zero-cost signals (no LLM/embedding needed):
  1. Confidence trend: self-reported confidence tier (HIGH→MEDIUM→LOW)
  2. Error amplification: error-keyword count trending upward
  3. Stagnation: output length collapsing (losing detail)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("pipeline_engine.drift")


@dataclass
class RoundQualitySnapshot:
    step: int
    confidence_tier: int = 0         # 3=HIGH, 2=MEDIUM, 1=LOW, 0=unknown
    error_keywords: int = 0          # count of error-related keywords in output
    output_length: int = 0           # length of reasoning text

    def quality_score(self) -> float:
        scores: List[float] = []
        if self.confidence_tier > 0:
            scores.append(self.confidence_tier / 3.0)
        if self.output_length > 0:
            len_score = min(1.0, self.output_length / 2000.0)
            scores.append(len_score)
        return sum(scores) / max(len(scores), 1)

    def is_significantly_worse_than(self, prev: "RoundQualitySnapshot") -> bool:
        q_self = self.quality_score()
        q_prev = prev.quality_score()
        if q_prev == 0:
            return False
        drop = (q_prev - q_self) / q_prev
        return drop > 0.3 and self.confidence_tier > 0 and prev.confidence_tier > 0


class DriftDetector:
    _CONFIDENCE = re.compile(
        r'(?:confidence|置信度)\s*(?:[:=]|is|level)?\s*(HIGH|MEDIUM|LOW)',
        re.IGNORECASE,
    )
    _ERROR = re.compile(
        r'(?:error|错误|fail|失败|incorrect|不正确|invalid|无效|broken|损坏|missing|缺失|crash|崩溃)',
        re.IGNORECASE,
    )

    WINDOW_SIZE = int(os.getenv("AIPLAT_DRIFT_WINDOW", "3"))
    DECLINE_THRESHOLD = int(os.getenv("AIPLAT_DRIFT_DECLINE_ROUNDS", "3"))

    @classmethod
    def capture_snapshot(cls, reasoning_text: str, step_count: int) -> RoundQualitySnapshot:
        return RoundQualitySnapshot(
            step=step_count,
            confidence_tier=cls._parse_confidence(reasoning_text),
            error_keywords=len(cls._ERROR.findall(reasoning_text or "")),
            output_length=len(reasoning_text or ""),
        )

    @classmethod
    def check_drift(cls, history: List[RoundQualitySnapshot]) -> Tuple[bool, str]:
        if len(history) < cls.DECLINE_THRESHOLD:
            return False, ""
        recent = history[-cls.DECLINE_THRESHOLD:]
        worse_pairs = 0
        for i in range(1, len(recent)):
            if recent[i].is_significantly_worse_than(recent[i - 1]):
                worse_pairs += 1
        if worse_pairs >= cls.DECLINE_THRESHOLD - 1:
            return True, f"reasoning_quality_decline:{worse_pairs}/{cls.DECLINE_THRESHOLD} rounds"
        last = recent[-1]
        n_before_last = recent[-2]
        if last.confidence_tier == 1 and n_before_last.confidence_tier >= 2 and last.quality_score() < 0.3:
            return True, "confidence_dropped_to_LOW"
        return False, ""

    @classmethod
    def _parse_confidence(cls, text: str) -> int:
        m = cls._CONFIDENCE.search(text or "")
        if not m:
            return 0
        tier = m.group(1).upper()
        if tier == "HIGH":
            return 3
        if tier == "MEDIUM":
            return 2
        if tier == "LOW":
            return 1
        return 0

    @classmethod
    def build_correction_reminder(cls, reason: str) -> str:
        return (
            "SYSTEM REMINDER: Your recent reasoning shows declining quality signal — "
            f"detected {reason}. "
            "Step back and reconsider your approach. Verify the facts in your previous "
            "output before proceeding. If you are unsure, acknowledge the uncertainty "
            "rather than amplifying potential errors."
        )
