"""P1 scoring semantics — metric families + engineering composite; accuracy gated until G2b."""
from __future__ import annotations

from app.scoring.composite import build_composite, metric_role
from app.scoring.g2b_accuracy import build_gold, wilson_ci
from app.scoring.report_compare import compare_reports, extract_composite_version
from app.scoring.report_stamp import (
    ensure_report_meta,
    ensure_report_scoring,
    infer_evidence_level,
)
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
    "compare_reports",
    "enrich_runner_result",
    "ensure_report_meta",
    "ensure_report_scoring",
    "extract_composite_version",
    "infer_evidence_level",
    "metric_role",
    "score_content_safety",
    "score_groundedness",
    "score_refusal",
    "score_text_quality",
    "wilson_ci",
]
