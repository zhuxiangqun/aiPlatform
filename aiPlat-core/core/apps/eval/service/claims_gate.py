"""L5 scope-bound accuracy/sufficiency claims gate (Object Contract §0.5 / §0.8).

Default posture: both claims stay false. This module only *evaluates* whether a
declared scope meets unlock prerequisites. Flipping claims to true requires
``explicit_authorize=True`` **and** all gates — callers that merge runtime
annotations must still force ``accuracy_claim=false`` unless they intentionally
opt into the authorized path for a bounded report.

Honesty: coverage ≠ sufficiency; incomplete coverage ≠ pass; fixture dry ≠ L5.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

CLAIMS_GATE_SCHEMA = "eval.claims_gate.v1"

# Protocol defaults (engineering); override via evidence["min_sample_n"].
DEFAULT_MIN_SAMPLE_N = 100

_REQUIRED_SCOPE_KEYS = (
    "object_type",
    "object_id",
    "object_version",
    "runtime_tier",
    "plan_id",
    "set_ids",
    "oracle_types",
    "dimensions",
    "sample_n",
)


def _as_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()] if str(v).strip() else []


def evaluate_l5_claims_gate(
    evidence: Optional[Mapping[str, Any]] = None,
    *,
    explicit_authorize: bool = False,
) -> Dict[str, Any]:
    """Evaluate whether scope-bound L5 claims *may* be authorized.

    Args:
        evidence: evidence 参数。
        explicit_authorize: explicit_authorize 参数。
    """
    ev = dict(evidence or {})
    missing: List[str] = []
    failed: List[str] = []

    for k in _REQUIRED_SCOPE_KEYS:
        if k not in ev or ev.get(k) in (None, "", [], {}):
            missing.append(f"scope.{k}")

    try:
        sample_n = int(ev.get("sample_n") or 0)
    except (TypeError, ValueError):
        sample_n = 0
        failed.append("sample_n_invalid")
    try:
        min_n = int(ev.get("min_sample_n") or DEFAULT_MIN_SAMPLE_N)
    except (TypeError, ValueError):
        min_n = DEFAULT_MIN_SAMPLE_N

    has_run = bool(ev.get("has_run_evidence"))
    if not has_run:
        failed.append("no_run_evidence")

    try:
        untested_n = int(ev.get("untested_applicable_n") or 0)
    except (TypeError, ValueError):
        untested_n = 0
        failed.append("untested_applicable_n_invalid")
    if untested_n > 0:
        failed.append("incomplete_coverage_untested")

    runtime_tier = str(ev.get("runtime_tier") or "").strip()
    fixture_only = bool(ev.get("fixture_only"))
    if fixture_only or runtime_tier == "fixture":
        failed.append("fixture_runtime_not_l5")
    if runtime_tier == "mixed":
        failed.append("mixed_runtime_not_l5")

    # runtime_claim true is required for accuracy (subject actually exercised)
    if not bool(ev.get("runtime_claim")):
        failed.append("runtime_claim_false")

    if sample_n < min_n:
        failed.append(f"sample_n<{min_n}")

    # §3.3 Case Pack claim gate: false/missing → cannot unlock accuracy
    if "claim_eligible" not in ev:
        failed.append("claim_eligible_unspecified")
    elif not bool(ev.get("claim_eligible")):
        failed.append("pack_not_claim_eligible")

    set_ids = _as_list(ev.get("set_ids"))
    oracle_types = _as_list(ev.get("oracle_types"))
    dimensions = _as_list(ev.get("dimensions"))
    if not set_ids:
        missing.append("scope.set_ids")
    if not oracle_types:
        missing.append("scope.oracle_types")
    if not dimensions:
        missing.append("scope.dimensions")

    scope = {
        "object_type": str(ev.get("object_type") or ""),
        "object_id": str(ev.get("object_id") or ""),
        "object_version": str(ev.get("object_version") or ""),
        "runtime_tier": runtime_tier,
        "plan_id": str(ev.get("plan_id") or ""),
        "set_ids": set_ids,
        "oracle_types": oracle_types,
        "dimensions": dimensions,
        "sample_n": sample_n,
        "min_sample_n": min_n,
    }

    gates_ok = not missing and not failed
    # Sufficiency additionally wants human_review or calibrated rubric flag
    human_review = bool(ev.get("human_review"))
    calibrated_rubric = bool(ev.get("calibrated_rubric"))
    sufficiency_extra_ok = human_review or calibrated_rubric
    if gates_ok and not sufficiency_extra_ok:
        # accuracy may still be eligible; sufficiency needs extra
        pass

    accuracy_eligible = gates_ok
    sufficiency_eligible = gates_ok and sufficiency_extra_ok
    if gates_ok and not sufficiency_extra_ok:
        failed_sufficiency = ["need_human_review_or_calibrated_rubric"]
    else:
        failed_sufficiency = []

    accuracy_claim = bool(explicit_authorize and accuracy_eligible)
    sufficiency_claim = bool(explicit_authorize and sufficiency_eligible)

    return {
        "schema": CLAIMS_GATE_SCHEMA,
        "scope": scope,
        "gates": {
            "scope_complete": not any(m.startswith("scope.") for m in missing),
            "has_run_evidence": has_run,
            "complete_coverage": untested_n == 0,
            "non_fixture_runtime": not (
                fixture_only or runtime_tier in ("fixture", "mixed", "")
            ),
            "runtime_claim": bool(ev.get("runtime_claim")),
            "sample_n_met": sample_n >= min_n,
            "claim_eligible": bool(ev.get("claim_eligible")),
            "human_review_or_calibrated_rubric": sufficiency_extra_ok,
        },
        "missing": missing,
        "failed": failed,
        "failed_sufficiency": failed_sufficiency,
        "accuracy_eligible": accuracy_eligible,
        "sufficiency_eligible": sufficiency_eligible,
        "explicit_authorize": bool(explicit_authorize),
        "accuracy_claim": accuracy_claim,
        "sufficiency_claim": sufficiency_claim,
        "claims_policy": {
            "accuracy_claim": accuracy_claim,
            "sufficiency_claim": sufficiency_claim,
            "note": (
                "L5 claims are scope-bound only; default false. "
                "authorize requires explicit_authorize + all gates. "
                "fixture/dry/mixed/incomplete coverage never unlock."
            ),
            "unlock_ref": "eval-object-contract-and-plan.md§0.5+§0.9",
        },
        "honesty": (
            "evaluate_l5_claims_gate ≠ auto publish certification; "
            "merge_runtime_fields and formal reports still default claim=false"
        ),
    }


def pack_claim_disclosure_from_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Report disclosure: pack_kind + claim_eligible per pack_ref (§3.3).

    Args:
        plan: plan 参数。
    """
    refs: List[Mapping[str, Any]] = []
    raw_refs = plan.get("pack_refs")
    if isinstance(raw_refs, list) and raw_refs:
        refs = [r for r in raw_refs if isinstance(r, Mapping)]
    elif isinstance(plan.get("pack_ref"), Mapping):
        refs = [plan["pack_ref"]]  # type: ignore[list-item]
    packs: List[Dict[str, Any]] = []
    for r in refs:
        kind = str(r.get("kind") or "unknown")
        packs.append(
            {
                "pack_id": r.get("pack_id"),
                "version": r.get("version") or r.get("pack_version"),
                "pack_kind": kind,
                "claim_eligible": bool(r.get("claim_eligible")),
                "hash": r.get("hash"),
            }
        )
    all_eligible = bool(packs) and all(bool(p["claim_eligible"]) for p in packs)
    kinds = sorted({str(p["pack_kind"]) for p in packs})
    return {
        "schema": "eval.pack_claim_disclosure.v1",
        "packs": packs,
        "pack_kinds": kinds,
        "claim_eligible": all_eligible,
        "note": (
            "Reports must disclose pack_kind + claim_eligible; "
            "claim_eligible=false packs excluded from accuracy aggregation; "
            "accuracy_claim stays closed unless L5 authorize + eligible packs"
        ),
    }


def claims_policy_stub(*, thin: bool = False, profile_source: str = "") -> Dict[str, Any]:
    """Default Plan claims_policy block (always locked false at compile).

    Args:
        thin: thin 参数。
        profile_source: profile_source 参数。
    """
    note = "Plan compile ≠ accuracy/sufficiency; special deferred → untested not fail"
    if thin:
        note += "; thin_contract"
    if profile_source:
        note += f"; profile_source={profile_source}"
    return {
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "claim_eligible": False,
        "note": note,
        "unlock_ref": "eval.claims_gate.v1 / eval-object-contract §0.9",
    }
