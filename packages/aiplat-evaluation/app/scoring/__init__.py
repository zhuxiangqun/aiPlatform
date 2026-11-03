"""P1 scoring semantics — metric families + engineering composite; accuracy gated until G2b."""
from __future__ import annotations

from app.scoring.composite import build_composite, metric_role
from app.scoring.g2b_accuracy import build_gold, wilson_ci
from app.scoring.semantics import (
    build_scoring_block,
    classify_metric,
    enrich_runner_result,
    score_content_safety,
    score_groundedness,
    score_refusal,
    score_text_quality,
)

__all__ = [
    "build_composite",
    "build_gold",
    "build_scoring_block",
    "classify_metric",
    "enrich_runner_result",
    "metric_role",
    "score_content_safety",
    "score_groundedness",
    "score_refusal",
    "score_text_quality",
    "wilson_ci",
]
