"""Evaluation Plan compiler (object-contract P2/P3).

Default: core + matched capability; special deferred → untested unless purpose
includes safety/perf/reliability or include_special=True.
P3: object_type adapters share the same Plan shape.
Does not change model selection.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_match import (
    case_spec_for_set,
    load_applicability_draft,
    match_eval_sets_for_target,
)
from core.apps.eval.service.claims_gate import claims_policy_stub
from core.apps.eval.service.object_adapters import (
    advisory_runtime_tier,
    default_set_ids_for_type,
)
from core.apps.eval.service.target_contract import normalize_target_contract

PLAN_SCHEMA_V1 = "eval.evaluation_plan.v1"
PLAN_SCHEMA_V2 = "eval.evaluation_plan.v2"
# New compiles emit v2 (nail 1). Keep V1 constant for projection / tests that pin schema.
PLAN_SCHEMA = PLAN_SCHEMA_V2

_SPECIAL_PURPOSE = frozenset({"safety", "perf", "performance", "reliability"})


def _purpose_allows_special(purpose: Sequence[str]) -> bool:
    have = {str(p).strip().lower() for p in purpose if str(p).strip()}
    return bool(have & _SPECIAL_PURPOSE)


def _plan_id_v1(contract: Mapping[str, Any], selected: Sequence[str], purpose: Sequence[str]) -> str:
    """Legacy fingerprint (set ids only) — do not use as v2 plan_id."""
    blob = json.dumps(
        {
            "object_id": contract.get("object_id"),
            "object_type": contract.get("object_type"),
            "object_version": contract.get("object_version"),
            "capabilities": contract.get("capabilities"),
            "permissions": contract.get("permissions"),
            "selected": list(selected),
            "purpose": list(purpose),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return "plan-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# Back-compat alias
_plan_id = _plan_id_v1


def compile_evaluation_plan(
    contract: Mapping[str, Any],
    *,
    set_ids: Optional[Sequence[str]] = None,
    purpose: Optional[Sequence[str]] = None,
    include_special: bool = False,
    live: bool = False,
    selection_strategy: str = "all",
    sample_n: Optional[int] = None,
    seed: Optional[int] = None,
    min_per_stratum: int = 1,
    on_insufficient: str = "error",
) -> Dict[str, Any]:
    """Compile Plan from target contract + applicability draft.

    Returns selected_cases to run, excluded_cases (not_applicable | untested deferred).
    When set_ids omitted, uses object_type defaults (agent/skill/api/generated_app/…).
    ``selection_strategy``: all|random|stratified (T12); shortfalls never silently
    rewrite quotas.
    """
    c = normalize_target_contract(contract)
    ot = str(c.get("object_type") or "")
    if set_ids is None:
        ids = default_set_ids_for_type(ot)
    else:
        ids = [str(x).strip() for x in set_ids if str(x).strip()]
    purposes = [
        str(p).strip()
        for p in (purpose or c.get("eval_purpose") or ["behavior", "regression"])
        if str(p).strip()
    ]
    allow_special = bool(include_special) or _purpose_allows_special(purposes)

    match = match_eval_sets_for_target(c, ids)
    selected: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    oracle_binding: Dict[str, Any] = {}

    selected_by_id = {
        str(x.get("set_id") or x.get("case_id")): x for x in match.get("selected_cases") or []
    }
    excluded_by_id = {
        str(x.get("set_id") or x.get("case_id")): x for x in match.get("excluded_cases") or []
    }

    for sid in ids:
        spec = case_spec_for_set(sid)
        pack = str(spec.get("pack") or "core")
        oracle = spec.get("oracle") if isinstance(spec.get("oracle"), dict) else {}
        if oracle.get("type"):
            oracle_binding[sid] = {"type": oracle.get("type")}

        if sid in excluded_by_id:
            row = dict(excluded_by_id[sid])
            row.setdefault("status", "not_applicable")
            row["pack"] = pack
            excluded.append(row)
            continue

        base = dict(
            selected_by_id.get(sid)
            or {"set_id": sid, "case_id": sid, "reasons": ["requires_satisfied"]}
        )
        base["pack"] = pack

        if pack == "special" and not allow_special:
            excluded.append(
                {
                    **base,
                    "status": "untested",
                    "reasons": [
                        "purpose_deferred_special",
                        f"pack=special; purpose={purposes}; include_special=false",
                    ],
                }
            )
            continue

        selected.append(
            {
                **base,
                "status": "selected",
                "reasons": list(base.get("reasons") or ["requires_satisfied"]),
            }
        )

    draft = load_applicability_draft()
    tr_list = list(c.get("target_runtime") or [])
    target_runtime = tr_list[0] if tr_list else "workspace_execute"
    runtime_tier = advisory_runtime_tier(
        object_type=ot, live=live, target_runtime=tr_list
    )

    # Thin contracts (no capabilities) → sufficiency stays false (always for P3).
    thin = not bool(c.get("capabilities")) and ot != "agent"

    profile_source = ""
    boundaries = c.get("boundaries") if isinstance(c.get("boundaries"), dict) else {}
    if isinstance(boundaries.get("note"), str) and "derived" in str(boundaries.get("note")):
        profile_source = "derived_hints"
    # Prefer explicit marker if callers stamped it on contract via eval_profile
    if c.get("profile_source"):
        profile_source = str(c.get("profile_source"))

    selected_set_ids = [x["set_id"] for x in selected]
    selection: Dict[str, Any] = {
        "mode": "legacy_sets",
        "set_ids": list(selected_set_ids),
        "filter": {},
        "sample_n": sample_n,
        "seed": seed,
        "strategy": str(selection_strategy or "all"),
        "min_per_stratum": int(min_per_stratum),
        "on_insufficient": str(on_insufficient or "error"),
    }

    from core.apps.eval.service.case_pack_hash import (
        compute_execution_fingerprint,
        compute_manifest_hash,
        compute_plan_id_v2,
    )
    from core.apps.eval.service.case_pack_legacy import (
        apply_manifest_sampling,
        expand_sets_to_manifest,
    )

    sample_manifest, pack_refs, coverage = expand_sets_to_manifest(
        selected_set_ids,
        claim_eligible=False,
        scope="global",
        kind="frozen",
        object_types=[ot] if ot else ["agent"],
    )
    sample_manifest, sample_meta = apply_manifest_sampling(
        sample_manifest,
        strategy=str(selection_strategy or "all"),
        sample_n=sample_n,
        seed=seed,
        min_per_stratum=int(min_per_stratum),
        on_insufficient=str(on_insufficient or "error"),
    )
    selection["quota_trace"] = sample_meta.get("quota_trace") or []
    if sample_meta.get("degraded"):
        selection["degraded"] = True
        selection["degraded_reasons"] = list(sample_meta.get("degraded_reasons") or [])
    coverage = dict(coverage or {})
    coverage["manifest_cases_after_sample"] = len(sample_manifest)

    manifest_hash = compute_manifest_hash(sample_manifest)
    pack_ref = pack_refs[0] if len(pack_refs) == 1 else None
    plan_id = compute_plan_id_v2(
        contract=c,
        purpose=purposes,
        selection=selection,
        pack_refs=pack_refs,
        manifest_hash=manifest_hash,
        plan_schema=PLAN_SCHEMA_V2,
    )
    execution_fingerprint = compute_execution_fingerprint(
        plan_id=plan_id,
        manifest_hash=manifest_hash,
        runner_id="compile",
        run_key="",
    )

    plan = {
        "schema": PLAN_SCHEMA_V2,
        "plan_id": plan_id,
        "plan_id_v1_projection": _plan_id_v1(c, selected_set_ids, purposes),
        "target_contract": c,
        "purpose": purposes,
        "include_special": bool(include_special),
        "special_allowed": allow_special,
        # selected_cases = legacy volume projection (NOT the execution list)
        "selected_cases": selected,
        "excluded_cases": excluded,
        "selection": selection,
        "pack_ref": pack_ref,
        "pack_refs": pack_refs,
        "sample_manifest": sample_manifest,
        "manifest_hash": manifest_hash,
        "execution_fingerprint": execution_fingerprint,
        "coverage": coverage,
        "legacy_set_projection": [
            {"set_id": s, "pack_id": (r.get("pack_id")), "version": r.get("version")}
            for r in pack_refs
            for s in [r.get("set_id")]
            if s
        ],
        "runtime_tier": runtime_tier,
        "target_runtime": target_runtime,
        "oracle_binding": oracle_binding,
        "eval_profile_source": profile_source or None,
        "claims_policy": claims_policy_stub(
            thin=thin, profile_source=str(profile_source or "")
        ),
        "match_report": match,
        "draft_schema": draft.get("schema"),
        "counts": {
            "selected": len(selected),
            "manifest_cases": len(sample_manifest),
            "not_applicable": sum(
                1 for x in excluded if x.get("status") == "not_applicable"
            ),
            "untested": sum(1 for x in excluded if x.get("status") == "untested"),
            "excluded": len(excluded),
            "total": len(selected) + len(excluded),
        },
        "honesty": (
            "Plan v2: sample_manifest is the sole execution list; "
            "selected_cases is legacy volume projection only. "
            "claim_eligible default false; accuracy_claim remains closed. "
            "derived_hints/unknown must not alone drive not_applicable on capabilities (§0.7)."
        ),
    }
    return plan


def project_plan_to_v1(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Compatibility projection: v1 shape only. Runner must not execute this."""
    p = dict(plan or {})
    return {
        "schema": PLAN_SCHEMA_V1,
        "plan_id": p.get("plan_id_v1_projection") or p.get("plan_id"),
        "target_contract": p.get("target_contract"),
        "purpose": p.get("purpose"),
        "include_special": p.get("include_special"),
        "special_allowed": p.get("special_allowed"),
        "selected_cases": p.get("selected_cases"),
        "excluded_cases": p.get("excluded_cases"),
        "runtime_tier": p.get("runtime_tier"),
        "target_runtime": p.get("target_runtime"),
        "oracle_binding": p.get("oracle_binding"),
        "eval_profile_source": p.get("eval_profile_source"),
        "claims_policy": p.get("claims_policy"),
        "match_report": p.get("match_report"),
        "draft_schema": p.get("draft_schema"),
        "counts": p.get("counts"),
        "projected_from": "v2",
        "honesty": (
            "v1 projection only — not an execution list; "
            "use sample_manifest from the v2 plan."
        ),
    }


def attach_evaluation_plan(out: Dict[str, Any], plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Stamp Plan fields onto an eval response (shared report contract)."""
    if not isinstance(out, dict):
        return out
    from core.apps.eval.service.claims_gate import pack_claim_disclosure_from_plan

    p = dict(plan or {})
    out["evaluation_plan"] = p
    out["plan_id"] = p.get("plan_id")
    if p.get("target_contract") is not None:
        out["target_contract"] = p.get("target_contract")
    if p.get("match_report") is not None:
        out["match_report"] = p.get("match_report")
    # §3.3: force pack_kind / claim_eligible disclosure; block false packs from claim
    disc = pack_claim_disclosure_from_plan(p)
    out["pack_claim_disclosure"] = disc
    out["pack_kinds"] = disc.get("pack_kinds") or []
    out["claim_eligible"] = bool(disc.get("claim_eligible"))
    if not out["claim_eligible"]:
        out["accuracy_claim"] = False
    else:
        out.setdefault("accuracy_claim", False)
    return out


def compile_plan_for_object(
    *,
    object_type: str,
    object_id: str,
    set_ids: Optional[Sequence[str]] = None,
    purpose: Optional[Sequence[str]] = None,
    include_special: bool = False,
    live: bool = False,
    capabilities: Optional[Sequence[str]] = None,
    tools: Optional[Sequence[str]] = None,
    permissions: Optional[Sequence[str]] = None,
    roles: Optional[Sequence[str]] = None,
    eval_profile: Optional[Mapping[str, Any]] = None,
    source_refs: Optional[Sequence[str]] = None,
    selection_strategy: str = "all",
    sample_n: Optional[int] = None,
    seed: Optional[int] = None,
    min_per_stratum: int = 1,
    on_insufficient: str = "error",
) -> Dict[str, Any]:
    """Adapter + compile in one call (P3 unified entry)."""
    from core.apps.eval.service.object_adapters import (
        build_contract_for_object_type,
        default_set_ids_for_type,
    )

    contract = build_contract_for_object_type(
        object_type=object_type,
        object_id=object_id,
        capabilities=capabilities,
        tools=tools,
        permissions=permissions,
        roles=roles,
        eval_profile=eval_profile,
        source_refs=source_refs,
    )
    ids = list(set_ids) if set_ids is not None else default_set_ids_for_type(object_type)
    return compile_evaluation_plan(
        contract,
        set_ids=ids,
        selection_strategy=selection_strategy,
        sample_n=sample_n,
        seed=seed,
        min_per_stratum=min_per_stratum,
        on_insufficient=on_insufficient,
        purpose=purpose,
        include_special=include_special,
        live=live,
    )
