"""
ComplexityRouter — Lightweight heuristic task complexity estimator.

Estimates task complexity from message content (no extra LLM call).
Used by ModelManager.select_by_purpose_list() to adjust local_bias multiplier.

Callers:
  - infra/management/model/manager.py (select_by_purpose_list scoring)
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ComplexityResult:
    level: str       # "simple" | "medium" | "complex"
    confidence: float  # 0.0-1.0


class ComplexityRouter:
    """Rule-based task complexity estimator. Zero external dependencies."""

    @staticmethod
    def estimate(messages: List[Dict[str, str]]) -> ComplexityResult:
        """Analyze messages and return complexity level.

        Rules (in priority order):
        1. Multi-step/reasoning keywords → complex
        2. Code generation keywords → complex
        3. Short classification task → simple
        4. JSON/structured output request → medium
        5. Default → medium
        """
        text = " ".join(m.get("content", "") for m in messages if m.get("content"))
        text_lower = text.lower()
        word_count = len(text)

        # Complex: multi-step, reasoning, planning, code
        complex_keywords = [
            r'\b(step|chain|reason|think|explain|analyze|evaluate|compare)\b',
            r'\b(code|function|script|python|javascript|implement|debug)\b',
            r'\b(plan|design|architecture|strategy|workflow|pipeline)\b',
        ]
        if any(_re.search(p, text_lower) for p in complex_keywords):
            return ComplexityResult("complex", 0.85)

        # Simple: short classification/lookup tasks
        if word_count < 200 and _re.search(r'classif|extract|list|what|which|find|get',
                                           text_lower):
            return ComplexityResult("simple", 0.90)

        # JSON/structured output → medium
        if _re.search(r'json|structur|format|output only|valid json', text_lower):
            return ComplexityResult("medium", 0.85)

        # Default
        return ComplexityResult("medium", 0.80)

    @staticmethod
    def local_bias_multiplier(level: str, prefer_local: bool) -> float:
        """Return the local bias score multiplier for a given complexity level.

        Simple tasks: 2x local preference (save money on trivial work)
        Complex tasks: 0.5x local preference (prioritize capability)
        Medium tasks: 1x (default)
        """
        if not prefer_local:
            return 1.0
        return {"simple": 2.0, "medium": 1.0, "complex": 0.5}.get(level, 1.0)
