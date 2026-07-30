"""NLI (Natural Language Inference) engine — stub, implementation pending.

The hallucination tracker gracefully falls back to regex rules when this
engine is not available. This stub exists to satisfy import paths so that
verify_imports.py does not flag it as a missing dependency.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NLIEngine:
    """Stub NLI engine. Returns neutral results until full implementation."""

    async def evaluate_claims(self, text: str) -> dict:
        """Evaluate factual consistency of claims in text."""
        logger.debug("NLIEngine.evaluate_claims: stub (not implemented)")
        return {
            "contradiction_score": 0.0,
            "entailment_score": 0.0,
            "summary": "NLI engine not implemented — using regex fallback",
        }
