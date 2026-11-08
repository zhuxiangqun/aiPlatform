"""Suite Profile → Plan v2 sample_manifest compiler (Case Pack P2).

Selects cases by fixed capability quotas; fail closed on shortfall.
Does not open accuracy_claim. claim_eligible forced false.
"""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.apps.eval.service.capability_case_bank import (
    PACK_ID,
    PACK_VERSION,
    PROFILE_ID,
    agent_regression_profile,
    build_agent_capability_cases,
)
from core.apps.eval.service.capability_id_map import (
    V1_IN_SCOPE,
    V1_OUT_OF_SCOPE,
    resolve_capability_id,
)
from core.apps.eval.service.case_pack_hash import (
    compute_case_hash,
    compute_execution_fingerprint,
    compute_manifest_hash,
    compute_pack_hash,
    compute_plan_id_v2,
)
from core.apps.eval.service.claims_gate import claims_policy_stub
from core.apps.eval.service.eval_plan import PLAN_SCHEMA_V2
from core.apps.eval.service.target_contract import (
    build_agent_target_contract,
    normalize_target_contract,
)

PROFILE_SCHEMA = "eval.suite_profile.v1"


class SuiteProfileCompileError(ValueError):
    """Profile compile fail-closed."""


def _cap_of(case: Mapping[str, Any]) -> str:
    caps = case.get("capabilities") or []
    if caps:
        return resolve_capability_id(str(caps[0]), fail_closed=False)
    req = case.get("requires") if isinstance(case.get("requires"), Mapping) else {}
    rcaps = list(req.get("capabilities") or []) if isinstance(req, Mapping) else []
    if rcaps:
        return resolve_capability_id(str(rcaps[0]), fail_closed=False)
    return str(case.get("category") or "").strip().lower()


def select_cases_for_profile(
    cases: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Apply fixed quotas; return selected cases + selection meta."""
    quotas_raw = profile.get("quotas") if isinstance(profile.get("quotas"), Mapping) else {}
    if not quotas_raw:
        raise SuiteProfileCompileError("profile.quotas required")
    strategy = str(profile.get("strategy") or "stratified").strip().lower() or "stratified"
    on_insufficient = str(profile.get("on_insufficient") or "error").strip().lower() or "error"
    seed = profile.get("seed")
    rng = random.Random(int(seed) if seed is not None else 0)

    quotas: Dict[str, int] = {}
    for k, v in quotas_raw.items():
        cid = resolve_capability_id(str(k), fail_closed=True)
        if cid in V1_OUT_OF_SCOPE or cid not in V1_IN_SCOPE:
            raise SuiteProfileCompileError(
                f"quota capability out of v1 measurable subset: {cid}"
            )
        try:
            n = int(v)
        except (TypeError, ValueError) as e:
            raise SuiteProfileCompileError(f"quota {cid} invalid: {v!r}") from e
        if n < 1:
            raise SuiteProfileCompileError(f"quota {cid} must be >= 1")
        quotas[cid] = n

    if bool(profile.get("claim_eligible")):
        raise SuiteProfileCompileError("profile.claim_eligible must be false in v1")

    by_cap: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for raw in cases:
        c = dict(raw)
        cap = _cap_of(c)
        if cap:
            by_cap[cap].append(c)

    selected: List[Dict[str, Any]] = []
    quota_trace: List[Dict[str, Any]] = []
    for cap, need in quotas.items():
        pool = list(by_cap.get(cap) or [])
        pool.sort(key=lambda x: str(x.get("case_id") or ""))
        if strategy in ("stratified", "random"):
            rng.shuffle(pool)
        available = len(pool)
        if available < need:
            if on_insufficient == "error":
                raise SuiteProfileCompileError(
                    f"insufficient cases for {cap}: need={need} have={available}"
                )
            take_n = available
            degraded = True
        else:
            take_n = need
            degraded = False
        taken = pool[:take_n]
        selected.extend(taken)
        quota_trace.append(
            {
                "capability_id": cap,
                "quota": need,
                "available": available,
                "taken": len(taken),
                "degraded": degraded,
            }
        )

    selected.sort(key=lambda x: str(x.get("case_id") or ""))
    meta = {
        "strategy": strategy,
        "seed": seed,
        "on_insufficient": on_insufficient,
        "quota_trace": quota_trace,
        "degraded": any(t.get("degraded") for t in quota_trace),
        "taken": len(selected),
    }
    return selected, meta


def compile_plan_from_suite_profile(
    *,
    profile: Optional[Mapping[str, Any]] = None,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    object_id: str = "agent.capability.target",
    object_version: str = "0.1.0",
) -> Dict[str, Any]:
    """Compile Plan v2 whose sample_manifest is the Profile-selected case list."""
    prof = dict(profile or agent_regression_profile())
    if str(prof.get("schema") or "") != PROFILE_SCHEMA:
        # allow missing schema if profile_id matches known
        if str(prof.get("profile_id") or "") != PROFILE_ID and not prof.get("quotas"):
            raise SuiteProfileCompileError("invalid suite profile")
        prof.setdefault("schema", PROFILE_SCHEMA)

    bank = list(cases) if cases is not None else build_agent_capability_cases()
    selected, selection_meta = select_cases_for_profile(bank, prof)

    pack_id = str(prof.get("pack_id") or PACK_ID)
    pack_version = str(prof.get("pack_version") or PACK_VERSION)
    ots = ["agent"]
    pack_hash = compute_pack_hash(
        pack_id=pack_id,
        version=pack_version,
        kind="frozen",
        claim_eligible=False,
        scope=str(prof.get("pack_scope") or "global"),
        object_types=ots,
        cases=selected,
    )

    sample_manifest: List[Dict[str, Any]] = []
    for c in selected:
        sample_manifest.append(
            {
                "case_id": str(c.get("case_id") or ""),
                "hash": compute_case_hash(c),
                "set_id": str(c.get("category") or _cap_of(c) or ""),
                "pack_id": pack_id,
                "pack_version": pack_version,
                "session_group": c.get("session_group"),
                "category": str(c.get("category") or _cap_of(c) or ""),
                "capability_id": _cap_of(c),
            }
        )

    caps = sorted({_cap_of(c) for c in selected if _cap_of(c)})
    contract = normalize_target_contract(
        build_agent_target_contract(
            object_id=object_id,
            object_version=object_version,
            capabilities=caps,
            eval_profile={
                "profile_source": "explicit",
                "capabilities": caps,
                "eval_purpose": ["behavior", "regression"],
            },
        )
    )

    selection = {
        "strategy": selection_meta.get("strategy"),
        "seed": selection_meta.get("seed"),
        "sample_n": len(sample_manifest),
        "quota_trace": selection_meta.get("quota_trace") or [],
        "degraded": bool(selection_meta.get("degraded")),
        "degraded_reasons": [],
        "profile_id": str(prof.get("profile_id") or PROFILE_ID),
    }
    if selection["degraded"]:
        selection["degraded_reasons"] = [
            f"shortfall:{t['capability_id']}"
            for t in selection["quota_trace"]
            if t.get("degraded")
        ]

    manifest_hash = compute_manifest_hash(sample_manifest)
    pack_refs = [
        {
            "pack_id": pack_id,
            "version": pack_version,
            "hash": pack_hash,
            "kind": "frozen",
            "claim_eligible": False,
            "scope": str(prof.get("pack_scope") or "global"),
            "profile_id": str(prof.get("profile_id") or PROFILE_ID),
        }
    ]
    plan_id = compute_plan_id_v2(
        contract=contract,
        purpose=["behavior", "regression"],
        selection=selection,
        pack_refs=pack_refs,
        manifest_hash=manifest_hash,
        plan_schema=PLAN_SCHEMA_V2,
    )
    execution_fingerprint = compute_execution_fingerprint(
        plan_id=plan_id,
        manifest_hash=manifest_hash,
        runner_id="suite_profile_compile",
        run_key=str(prof.get("profile_id") or PROFILE_ID),
    )

    coverage = {
        "cases": len(selected),
        "manifest_cases_after_sample": len(sample_manifest),
        "by_capability": {
            t["capability_id"]: {"quota": t["quota"], "taken": t["taken"]}
            for t in selection["quota_trace"]
        },
        "sets": {},
    }

    return {
        "schema": PLAN_SCHEMA_V2,
        "ok": True,
        "plan_id": plan_id,
        "profile_id": str(prof.get("profile_id") or PROFILE_ID),
        "suite_profile": {
            "schema": prof.get("schema"),
            "profile_id": prof.get("profile_id"),
            "pack_id": pack_id,
            "pack_version": pack_version,
            "quotas": prof.get("quotas"),
            "strategy": prof.get("strategy"),
            "seed": prof.get("seed"),
            "claim_eligible": False,
        },
        "target_contract": contract,
        "purpose": ["behavior", "regression"],
        "selected_cases": [
            {
                "set_id": str(c.get("category") or _cap_of(c)),
                "case_id": c.get("case_id"),
                "pack": "capability",
                "status": "selected",
                "reasons": ["profile_quota"],
            }
            for c in selected
        ],
        "excluded_cases": [],
        "selection": selection,
        "pack_ref": pack_refs[0],
        "pack_refs": pack_refs,
        "sample_manifest": sample_manifest,
        "manifest_hash": manifest_hash,
        "execution_fingerprint": execution_fingerprint,
        "coverage": coverage,
        "claims_policy": claims_policy_stub(thin=False, profile_source="explicit"),
        "claim_eligible": False,
        "accuracy_claim": False,
        "counts": {
            "selected": len(selected),
            "manifest_cases": len(sample_manifest),
            "excluded": 0,
            "total": len(selected),
        },
        "honesty": (
            "Plan v2 from Suite Profile: sample_manifest is sole execution list; "
            "claim_eligible=false; accuracy_claim closed; quotas fixed (v1)."
        ),
    }
