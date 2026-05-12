"""
Scoring dimensions registry for evaluation.

Scoring dimensions are read from:

1. PipelineStageConfig.scoring_dimensions (pipeline context)
2. AIPLAT_EVAL_DIMENSIONS environment variable

Per CLAUDE.md §5.29: All scoring dimensions MUST be config-driven,
not hardcoded in engine/evaluation code.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def _env_dimensions() -> Optional[List[Dict[str, Any]]]:
    raw = os.getenv("AIPLAT_EVAL_DIMENSIONS", "")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def get_scoring_dimensions(
    overrides: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Return the active scoring dimensions list.

    Priority: overrides > AIPLAT_EVAL_DIMENSIONS env var.

    Each dimension is a dict with:
        name: str           dimension name
        weight: float       relative weight in overall score
        threshold_min: float optional minimum threshold
    """
    if overrides:
        return overrides
    env = _env_dimensions()
    if env is not None:
        return env
    return []


def get_dimension_names(
    overrides: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    return [d["name"] for d in get_scoring_dimensions(overrides)]


def get_dimension_weights(
    overrides: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, float]:
    return {d["name"]: d.get("weight", 0.0) for d in get_scoring_dimensions(overrides)}


def get_dimension_thresholds(
    overrides: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, float]:
    return {d["name"]: d.get("threshold_min", 0.0) for d in get_scoring_dimensions(overrides)}


def build_default_score_schema(
    overrides: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a score schema dict like {name: 0, name: 0, ..., overall: 0}."""
    dims = get_scoring_dimensions(overrides)
    score: Dict[str, Any] = {"overall": 0}
    for d in dims:
        score[d["name"]] = d.get("threshold_min", 0.0)
    return score


def compute_overall_score(
    score_obj: Dict[str, Any],
    overrides: Optional[List[Dict[str, Any]]] = None,
) -> float:
    """Weighted average of dimension scores."""
    dims = get_scoring_dimensions(overrides)
    total_weight = 0.0
    weighted_sum = 0.0
    for d in dims:
        name = d["name"]
        weight = d.get("weight", 0.0)
        val = float(score_obj.get(name, 0) or 0)
        weighted_sum += val * weight
        total_weight += weight
    if total_weight > 0:
        return round(weighted_sum / total_weight, 2)
    # Fallback: simple average
    vals = [float(score_obj.get(d["name"], 0) or 0) for d in dims]
    vals = [v for v in vals if v > 0]
    return round(sum(vals) / len(vals), 2) if vals else 0.0
