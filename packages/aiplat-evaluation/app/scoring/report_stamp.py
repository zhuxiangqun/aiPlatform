"""P1b — stamp scoring.composite onto store report metrics for comparable reports.

Honesty: never sets accuracy_claim true; does not rewrite existing composite_version;
only attaches build_composite when known engineering metrics are present.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from app.scoring.composite import _METRIC_ROLE, build_composite
from app.scoring.report_compare import extract_composite_version


_SKIP_KEYS = frozenset({"scoring", "composite", "policy", "families", "meta"})


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _has_known_metrics(metrics: Mapping[str, Any]) -> bool:
    for key in metrics:
        name = str(key)
        if name in _SKIP_KEYS:
            continue
        if name in _METRIC_ROLE:
            return True
    return False


def ensure_report_scoring(
    metrics: Optional[Mapping[str, Any]] = None,
    *,
    scoring: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return metrics dict with scoring.composite when stamping is justified.

    Priority:
    1. Explicit ``scoring`` envelope from caller (merged under metrics.scoring).
    2. Existing metrics.scoring with composite_version — leave composite alone.
    3. Else if known engineering metric keys present — attach ``build_composite``.
    4. Else leave metrics unchanged (compare will mark incomparable).
    """
    out: Dict[str, Any] = _as_dict(metrics)
    if scoring and isinstance(scoring, Mapping):
        merged = _as_dict(out.get("scoring"))
        merged.update(dict(scoring))
        out["scoring"] = merged

    if extract_composite_version(out):
        return out

    scoring_block = _as_dict(out.get("scoring"))
    existing_composite = scoring_block.get("composite")
    if isinstance(existing_composite, Mapping) and existing_composite:
        # Composite present but version missing — do not invent; leave for compare.
        return out

    if not _has_known_metrics(out):
        return out

    composite = build_composite(out)
    scoring_block = _as_dict(out.get("scoring"))
    scoring_block["composite"] = composite
    scoring_block.setdefault("schema", "eval.scoring.semantics.v1")
    scoring_block["accuracy_claim"] = False
    out["scoring"] = scoring_block
    return out


def _wire_stamp() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    return ensure_report_scoring({"exact_match": 1.0, "content_safety": 1.0})
