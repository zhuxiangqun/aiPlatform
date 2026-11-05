"""P1b — stamp scoring.composite + version meta onto store report metrics.

Honesty: never sets accuracy_claim true; does not rewrite existing composite_version;
only attaches build_composite when known engineering metrics are present.
evidence_level is EET tag (smoke/fixture/gold/human) — not a release gate grade.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from app.scoring.composite import _METRIC_ROLE, build_composite, metric_role
from app.scoring.report_compare import extract_composite_version


_SKIP_KEYS = frozenset({"scoring", "composite", "policy", "families", "meta"})
_META_KEYS = (
    "runner_id",
    "runner_version",
    "judge_id",
    "judge_version",
    "dataset_id",
    "dataset_version",
    "schema_version",
    "composite_version",
    "evidence_level",
)
_EVIDENCE_LEVELS = frozenset({"smoke", "fixture", "gold", "human"})
_SMOKE_RUNNER_HINTS = ("arena", "length", "smoke", "heuristic")
_GOLD_RUNNER_HINTS = ("gold", "code_review_gold", "exact")
_HUMAN_RUNNER_HINTS = ("g2b", "human", "blind", "preference")
_GOLD_METRIC_HINTS = frozenset({"exact_match", "groundedness", "gold_n"})


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


def _normalize_evidence_level(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    level = raw.strip().lower()
    if level.startswith("eet-"):
        # EET-1..4 → smoke/fixture/gold/human
        digit = level.replace("eet-", "").strip()
        mapping = {"1": "smoke", "2": "fixture", "3": "gold", "4": "human"}
        level = mapping.get(digit, level)
    return level if level in _EVIDENCE_LEVELS else None


def infer_evidence_level(
    metrics: Optional[Mapping[str, Any]] = None,
    *,
    meta: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Infer EET evidence_level; never invents ``human`` without an explicit signal.

    Priority: explicit meta/metrics → runner hints → metric roles.
    Returns None when there is no justified tag (caller must not invent).
    """
    out = _as_dict(metrics)
    bucket = _as_dict(out.get("meta"))
    if meta and isinstance(meta, Mapping):
        for key, raw in meta.items():
            if raw is None or raw == "":
                continue
            bucket[str(key)] = raw

    for source in (bucket.get("evidence_level"), out.get("evidence_level")):
        level = _normalize_evidence_level(source)
        if level:
            return level

    runner = str(bucket.get("runner_id") or out.get("runner_id") or "").lower()
    judge = str(bucket.get("judge_id") or out.get("judge_id") or "").lower()
    blob = f"{runner} {judge}"
    if any(h in blob for h in _HUMAN_RUNNER_HINTS):
        return "human"
    if any(h in blob for h in _SMOKE_RUNNER_HINTS):
        return "smoke"
    if any(h in blob for h in _GOLD_RUNNER_HINTS):
        return "gold"

    known = [str(k) for k in out if str(k) not in _SKIP_KEYS and str(k) in _METRIC_ROLE]
    if not known:
        return None
    roles = {name: metric_role(name) for name in known}
    scored = [n for n, r in roles.items() if r == "scored"]
    if not scored:
        return "smoke"
    if any(n in _GOLD_METRIC_HINTS for n in scored):
        return "gold"
    return "fixture"


def ensure_report_meta(
    metrics: Optional[Mapping[str, Any]] = None,
    *,
    meta: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize runner/judge/dataset/schema/evidence stamps under ``metrics.meta``.

    Merges explicit ``meta``, promotes known keys from metrics root, and copies
    ``composite_version`` when scoring already carries it. Does not invent versions.
    Stamps ``evidence_level`` when inferable; never upgrades to human without signal.
    """
    out: Dict[str, Any] = _as_dict(metrics)
    bucket = _as_dict(out.get("meta"))
    if meta and isinstance(meta, Mapping):
        for key, raw in meta.items():
            if raw is None or raw == "":
                continue
            bucket[str(key)] = raw
    for key in _META_KEYS:
        if key in out and out[key] not in (None, "") and key not in bucket:
            bucket[key] = out[key]
    ver = extract_composite_version(out)
    if ver:
        bucket.setdefault("composite_version", ver)
    if "evidence_level" not in bucket or not _normalize_evidence_level(bucket.get("evidence_level")):
        inferred = infer_evidence_level(out, meta=bucket)
        if inferred:
            bucket["evidence_level"] = inferred
    else:
        bucket["evidence_level"] = _normalize_evidence_level(bucket.get("evidence_level"))
    if bucket:
        out["meta"] = bucket
    return out


def ensure_report_scoring(
    metrics: Optional[Mapping[str, Any]] = None,
    *,
    scoring: Optional[Mapping[str, Any]] = None,
    meta: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Stamp composite when justified, then normalize version meta (P1b).

    Priority for composite:
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

    if not extract_composite_version(out):
        scoring_block = _as_dict(out.get("scoring"))
        existing_composite = scoring_block.get("composite")
        if not (isinstance(existing_composite, Mapping) and existing_composite):
            if _has_known_metrics(out):
                composite = build_composite(out)
                scoring_block = _as_dict(out.get("scoring"))
                scoring_block["composite"] = composite
                scoring_block.setdefault("schema", "eval.scoring.semantics.v1")
                scoring_block["accuracy_claim"] = False
                out["scoring"] = scoring_block

    return ensure_report_meta(out, meta=meta)


def _wire_stamp() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    return ensure_report_scoring(
        {"exact_match": 1.0, "content_safety": 1.0, "runner_id": "prompt_eval"},
        meta={"runner_version": "v0"},
    )