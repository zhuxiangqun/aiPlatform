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
from core.apps.eval.service.object_adapters import (
    advisory_runtime_tier,
    default_set_ids_for_type,
)
from core.apps.eval.service.target_contract import normalize_target_contract

PLAN_SCHEMA = "eval.evaluation_plan.v1"

_SPECIAL_PURPOSE = frozenset({"safety", "perf", "performance", "reliability"})


def _purpose_allows_special(purpose: Sequence[str]) -> bool:
    have = {str(p).strip().lower() for p in purpose if str(p).strip()}
    return bool(have & _SPECIAL_PURPOSE)


def _plan_id(contract: Mapping[str, Any], selected: Sequence[str], purpose: Sequence[str]) -> str:
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


def compile_evaluation_plan(
    contract: Mapping[str, Any],
    *,
    set_ids: Optional[Sequence[str]] = None,
    purpose: Optional[Sequence[str]] = None,
    include_special: bool = False,
    live: bool = False,
) -> Dict[str, Any]:
    """Compile Plan from target contract + applicability draft.

    Returns selected_cases to run, excluded_cases (not_applicable | untested deferred).
    When set_ids omitted, uses object_type defaults (agent/skill/api/generated_app/…).
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

    plan = {
        "schema": PLAN_SCHEMA,
        "plan_id": _plan_id(c, [x["set_id"] for x in selected], purposes),
        "target_contract": c,
        "purpose": purposes,
        "include_special": bool(include_special),
        "special_allowed": allow_special,
        "selected_cases": selected,
        "excluded_cases": excluded,
        "runtime_tier": runtime_tier,
        "target_runtime": target_runtime,
        "oracle_binding": oracle_binding,
        "eval_profile_source": profile_source or None,
        "claims_policy": {
            "accuracy_claim": False,
            "sufficiency_claim": False,
            "note": (
                "Plan compile ≠ accuracy/sufficiency; special deferred → untested not fail"
                + ("; thin_contract" if thin else "")
                + (f"; profile_source={profile_source}" if profile_source else "")
            ),
        },
        "match_report": match,
        "draft_schema": draft.get("schema"),
        "counts": {
            "selected": len(selected),
            "not_applicable": sum(
                1 for x in excluded if x.get("status") == "not_applicable"
            ),
            "untested": sum(1 for x in excluded if x.get("status") == "untested"),
            "excluded": len(excluded),
            "total": len(selected) + len(excluded),
        },
        "honesty": (
            "P3 Plan: same schema for agent/skill/api/generated_app/…; "
            "default core+matched capability; special needs purpose "
            "safety|perf|reliability or include_special. Excluded not executed."
        ),
    }
    return plan


def attach_evaluation_plan(out: Dict[str, Any], plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Stamp Plan fields onto an eval response (shared report contract)."""
    if not isinstance(out, dict):
        return out
    p = dict(plan or {})
    out["evaluation_plan"] = p
    out["plan_id"] = p.get("plan_id")
    if p.get("target_contract") is not None:
        out["target_contract"] = p.get("target_contract")
    if p.get("match_report") is not None:
        out["match_report"] = p.get("match_report")
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
        purpose=purpose,
        include_special=include_special,
        live=live,
    )
