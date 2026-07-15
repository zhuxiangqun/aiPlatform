"""
QualityValidator — Programmatic output quality assessment for LLM routing.

Provides per-purpose validators that score LLM responses without human labeling.
Used by model_injection.generate_with_fallback() to feed quality_scores back
into ModelManager's scoring algorithm.

Callers:
  - core/harness/utils/model_injection.py (generate_with_fallback success path)
"""

from __future__ import annotations

import re as _re
import json as _json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class QualityResult:
    ok: bool
    score_delta: float     # [-1.0, +1.0] — how much to adjust quality_scores
    details: Dict[str, Any] = field(default_factory=dict)


class QualityValidator:
    """Programmatic output quality assessment — no human labeling needed."""

    VALIDATORS = {
        "ontology_gen": "_validate_ontology_result",
        "chat": "_validate_chat_result",
        "clarify": "_validate_clarify_result",
    }

    @classmethod
    def validate(cls, purpose: str, response_text: str, context: dict = None) -> QualityResult:
        """Validate LLM output for a given purpose. Returns QualityResult with score delta."""
        if purpose not in cls.VALIDATORS:
            return QualityResult(ok=True, score_delta=0.0,
                                details={"reason": "no_validator_for_purpose"})

        fn_name = cls.VALIDATORS[purpose]
        fn = getattr(cls, fn_name)
        return fn(response_text, context or {})

    @staticmethod
    def _validate_ontology_result(response_text: str, context: dict) -> QualityResult:
        """Validate ontology classification output.
        
        Checks: valid JSON, has suggestions/pages key, each entry has title+category.
        """
        try:
            # 1. Extract JSON from response
            clean = response_text.strip()
            bs, be = clean.find('{'), clean.rfind('}')
            if bs >= 0 and be > bs:
                clean = clean[bs:be + 1]
            match = _re.search(r'\{[\s\S]*\}', clean)
            if not match:
                return QualityResult(ok=False, score_delta=-0.08,
                                    details={"reason": "no_json_found"})

            data = _json.loads(match.group(0))
            if isinstance(data, list):
                data = {"suggestions": data}

            suggestions = data.get("suggestions") or data.get("pages") or []
            if not suggestions:
                return QualityResult(ok=False, score_delta=-0.04,
                                    details={"reason": "empty_suggestions"})

            # 2. Validate each suggestion has required fields
            valid = 0
            for s in suggestions:
                if isinstance(s, dict) and s.get("title") and s.get("category"):
                    valid += 1

            ratio = valid / max(len(suggestions), 1)

            # Score delta: range [-0.06, +0.06]
            # Valid JSON + suggestions = baseline neutral
            # High valid ratio → positive delta, low ratio → negative delta
            delta = (ratio - 0.5) * 0.08
            delta = max(-0.06, min(0.06, delta))

            return QualityResult(
                ok=True, score_delta=delta,
                details={"suggestions_count": len(suggestions), "valid_ratio": ratio,
                         "valid_count": valid}
            )
        except (_json.JSONDecodeError, Exception) as e:
            return QualityResult(ok=False, score_delta=-0.06,
                                details={"reason": "json_parse_fail", "error": str(e)[:80]})

    @staticmethod
    def _validate_chat_result(response_text: str, context: dict) -> QualityResult:
        """Validate general chat output.
        
        Checks: non-empty response, reasonable length, not just error messages.
        """
        text = response_text.strip()
        if not text:
            return QualityResult(ok=False, score_delta=-0.04,
                                details={"reason": "empty_response"})

        # Penalize common error patterns
        error_patterns = ["I cannot", "I'm unable", "not possible", "抱歉", "无法"]
        hits = sum(1 for p in error_patterns if p.lower() in text.lower())

        if hits >= 2:
            return QualityResult(ok=False, score_delta=-0.03,
                                details={"reason": "error_patterns_detected", "hits": hits})

        # Reward meaningful length (not too short, not too long)
        length = len(text)
        if length < 20:
            delta = -0.02
        elif length > 50:
            delta = 0.01
        else:
            delta = 0.0

        return QualityResult(ok=True, score_delta=delta,
                            details={"length": length})

    @staticmethod
    def _validate_clarify_result(response_text: str, context: dict) -> QualityResult:
        """Validate clarify output — check for structured JSON or useful narrative.
        
        Rewards well-structured JSON with clear follow-up questions.
        Punishes empty/irrelevant responses.
        """
        text = response_text.strip()
        if not text or len(text) < 10:
            return QualityResult(ok=False, score_delta=-0.06,
                                details={"reason": "empty_or_too_short"})

        # Check for well-structured JSON with questions field
        if _re.search(r'\{"questions"\s*:\s*\[.*?\],\s*"next"', text, _re.DOTALL):
            return QualityResult(ok=True, score_delta=0.04,
                                details={"reason": "well_structured_json"})

        # Check for any valid JSON object
        bs, be = text.find('{'), text.rfind('}')
        if bs >= 0 and be > bs:
            try:
                _json.loads(text[bs:be + 1])
                return QualityResult(ok=True, score_delta=0.02,
                                    details={"reason": "has_valid_json"})
            except Exception:
                pass

        # Natural language — check if it's useful (non-trivial length, contains clarifying keywords)
        clarify_keywords = ['追问', '问题', '建议', '步骤', '分析', '确认', '检查', '评估',
                            'fde', '客户', '流程', '需求', '方案', '补充', '解决', '处理']
        match_count = sum(1 for kw in clarify_keywords if kw in text)
        if len(text) > 100 and match_count >= 2:
            return QualityResult(ok=True, score_delta=0.01,
                                details={"reason": "useful_narrative", "keyword_hits": match_count})

        if len(text) > 50 and match_count >= 1:
            return QualityResult(ok=True, score_delta=0.005,
                                details={"reason": "acceptable_narrative"})

        return QualityResult(ok=True, score_delta=-0.01,
                            details={"reason": "too_short_or_irrelevant"})


# ── Quality score storage with EWMA ─────────────────────────────────

class QualityTracker:
    """Persistent quality score tracking with EWMA (Exponential Weighted Moving Average)."""

    def __init__(self, alpha: float = 0.3):
        """alpha: EWMA smoothing factor. Lower = smoother, slower to react."""
        self._alpha = alpha
        self._scores: Dict[str, Dict[str, float]] = {}  # model_name → {purpose: score}

    def initial_score(self, model_name: str) -> float:
        """Cold-start bootstrap: give known-good models a slight initial advantage."""
        trusted_prefixes = ["qwen", "deepseek", "gemma", "gpt", "claude"]
        return 0.05 if any(model_name.startswith(p) for p in trusted_prefixes) else 0.0

    def get(self, model_name: str, purpose: str) -> float:
        """Get current quality score. Returns initial bootstrap if no history."""
        if model_name not in self._scores:
            self._scores[model_name] = {}
        if purpose not in self._scores[model_name]:
            self._scores[model_name][purpose] = self.initial_score(model_name)
        return self._scores[model_name][purpose]

    def update(self, model_name: str, purpose: str, delta: float):
        """Update score using EWMA: new = old * (1-α) + delta * α."""
        old = self.get(model_name, purpose)
        self._scores[model_name][purpose] = old * (1 - self._alpha) + delta * self._alpha

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        return dict(self._scores)


# Global singleton
_quality_tracker = QualityTracker()


def get_quality_tracker() -> QualityTracker:
    return _quality_tracker
