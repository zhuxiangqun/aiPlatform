"""Case applicability + MatchReport (eval-object-contract P0).

Matching only — does not change which tasks execute (Plan filter = P2).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.capability_id_map import (
    UnknownCapabilityId,
    capability_match_set,
    resolve_capability_id,
)
from core.apps.eval.service.target_contract import normalize_target_contract

APPLICABILITY_SCHEMA = "eval.case_applicability_draft.v1"
MATCH_REPORT_SCHEMA = "eval.match_report.v1"

_SAFETY_EVAL_MARKERS = frozenset(
    {
        "safety",
        "permission",
        "permissions",
        "refusal",
        "refuse",
        "handoff",
        "boundary",
    }
)


def _str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, (list, tuple, set)):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    s = str(v).strip()
    return [s] if s else []


def _draft_path() -> Path:
    # aiPlat-core/core/apps/eval/service → …/core/engine/eval_sets
    return (
        Path(__file__).resolve().parents[3]
        / "engine"
        / "eval_sets"
        / "applicability_draft.json"
    )


@lru_cache(maxsize=1)
def load_applicability_draft() -> Dict[str, Any]:
    path = _draft_path()
    if not path.is_file():
        return {"schema": APPLICABILITY_SCHEMA, "sets": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("applicability_draft must be an object")
    return data


def clear_applicability_draft_cache() -> None:
    load_applicability_draft.cache_clear()


def case_spec_for_set(set_id: str, *, draft: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Resolve set-level applicability draft into a case-like spec."""
    sid = (set_id or "").strip()
    blob = dict(draft or load_applicability_draft())
    sets = blob.get("sets") if isinstance(blob.get("sets"), dict) else {}
    row = sets.get(sid) if isinstance(sets.get(sid), dict) else {}
    applies = row.get("applies_to") if isinstance(row.get("applies_to"), dict) else {}
    requires = row.get("requires") if isinstance(row.get("requires"), dict) else {}
    runtime = requires.get("runtime") if isinstance(requires.get("runtime"), dict) else {}
    return {
        "case_id": sid,
        "set_id": sid,
        "applies_to": {
            "object_types": _str_list(applies.get("object_types") or ["agent"]),
        },
        "requires": {
            "capabilities": _str_list(requires.get("capabilities")),
            "tools": _str_list(requires.get("tools")),
            "permissions": _str_list(requires.get("permissions")),
            "runtime": {
                "check": str(runtime.get("check") or "target_runtime").strip()
                or "target_runtime",
                "any_of": _str_list(runtime.get("any_of") or runtime.get("target_runtime_any")),
            },
        },
        "evaluates": _str_list(row.get("evaluates")),
        "pack": str(row.get("pack") or "core").strip() or "core",
        "risk_level": str(row.get("risk_level") or "low").strip() or "low",
        "obligation": str(row.get("obligation") or "").strip(),
        "oracle": dict(row.get("oracle") or {}) if isinstance(row.get("oracle"), dict) else {},
        "requires_contract": bool(row.get("requires_contract", True)),
    }


def _missing_required(have: Sequence[str], need: Sequence[str]) -> List[str]:
    have_set = {str(x).strip().lower() for x in have if str(x).strip()}
    return [n for n in need if n.strip().lower() not in have_set]


def _missing_capabilities(have: Sequence[str], need: Sequence[str]) -> List[str]:
    """Compare on canonical ids (legacy alias → canonical). Report canonical miss."""
    have_set = capability_match_set(have)
    missing: List[str] = []
    for n in need:
        raw = str(n or "").strip()
        if not raw:
            continue
        try:
            cid = resolve_capability_id(raw, fail_closed=True)
        except UnknownCapabilityId:
            cid = raw.lower()
        if cid not in have_set:
            missing.append(cid)
    return missing


def _evaluates_safety(evaluates: Sequence[str]) -> bool:
    for e in evaluates:
        el = str(e).strip().lower()
        if el in _SAFETY_EVAL_MARKERS or any(m in el for m in _SAFETY_EVAL_MARKERS):
            return True
    return False


def _refuse_or_handoff_exception(spec: Mapping[str, Any]) -> bool:
    """Special pack safety obligation: missing execute perms still applicable."""
    pack = str(spec.get("pack") or "").strip().lower()
    obligation = str(spec.get("obligation") or "").strip().lower()
    return (
        pack == "special"
        and obligation == "refuse_or_handoff"
        and _evaluates_safety(_str_list(spec.get("evaluates")))
    )


def _capability_requirements_authoritative(contract: Mapping[str, Any]) -> bool:
    """Only an explicit eval_profile may treat missing capabilities as hard N/A.

    §0.7: derived_hints / unknown profiles are suggestion signals — absence of a
    derived tag ≠ confirmed lack of capability. Boundaries.derived=true also
    marks a non-authoritative capability list.
    """
    ps = str(contract.get("profile_source") or "").strip().lower()
    if ps == "explicit":
        return True
    if ps == "derived_hints":
        return False
    boundaries = (
        contract.get("boundaries") if isinstance(contract.get("boundaries"), dict) else {}
    )
    if boundaries.get("derived") is True:
        return False
    # No profile_source (or other values): treat capability gaps as unconfirmed.
    return False


def match_case(
    contract: Mapping[str, Any],
    case_spec: Mapping[str, Any],
) -> Dict[str, Any]:
    """Match one case/set spec against a target contract.

    Returns decision ``selected`` | ``not_applicable`` with reasons.
    """
    c = normalize_target_contract(contract)
    spec = dict(case_spec or {})
    applies = spec.get("applies_to") if isinstance(spec.get("applies_to"), dict) else {}
    types = _str_list(applies.get("object_types"))
    hard_reasons: List[str] = []
    advisory_reasons: List[str] = []
    case_id = str(spec.get("case_id") or spec.get("set_id") or "").strip()

    if types and c["object_type"] not in types:
        hard_reasons.append(f"object_type_mismatch:{c['object_type']} not in {types}")
        return {
            "case_id": case_id,
            "set_id": str(spec.get("set_id") or case_id),
            "decision": "not_applicable",
            "reasons": hard_reasons,
            "pack": str(spec.get("pack") or ""),
            "obligation_exception_applied": False,
        }

    requires = spec.get("requires") if isinstance(spec.get("requires"), dict) else {}
    miss_caps = _missing_capabilities(
        c["capabilities"], _str_list(requires.get("capabilities"))
    )
    miss_tools = _missing_required(c["tools"], _str_list(requires.get("tools")))
    miss_perms = _missing_required(c["permissions"], _str_list(requires.get("permissions")))

    runtime = requires.get("runtime") if isinstance(requires.get("runtime"), dict) else {}
    any_of = _str_list(runtime.get("any_of"))
    check = str(runtime.get("check") or "target_runtime").strip() or "target_runtime"
    miss_runtime: List[str] = []
    if any_of:
        if check == "runtime_tier":
            # P0 advisory: contracts declare target_runtime; actual tier matched at run time.
            have = set(x.lower() for x in c["target_runtime"])
            if not any(a.lower() in have for a in any_of):
                miss_runtime = list(any_of)
                hard_reasons.append(
                    f"runtime_mismatch:check=runtime_tier(deferred_to_target_runtime) need_any={any_of} have={c['target_runtime']}"
                )
        else:
            have = set(x.lower() for x in c["target_runtime"])
            if not any(a.lower() in have for a in any_of):
                miss_runtime = list(any_of)
                hard_reasons.append(
                    f"runtime_mismatch:check=target_runtime need_any={any_of} have={c['target_runtime']}"
                )

    caps_authoritative = _capability_requirements_authoritative(c)
    profile_source = str(c.get("profile_source") or "").strip() or "unknown"
    for m in miss_caps:
        if caps_authoritative:
            hard_reasons.append(f"missing_capability:{m}")
        else:
            advisory_reasons.append(
                f"capability_unconfirmed:{m}:profile_source={profile_source}"
            )
    for m in miss_tools:
        hard_reasons.append(f"missing_tool:{m}")
    for m in miss_perms:
        hard_reasons.append(f"missing_permission:{m}")

    obligation_applied = False
    if hard_reasons:
        only_perm = (
            bool(miss_perms)
            and not any(r.startswith("missing_capability:") for r in hard_reasons)
            and not miss_tools
            and not miss_runtime
            and all(
                r.startswith("missing_permission:") or r.startswith("waived:")
                for r in hard_reasons
            )
        )
        if only_perm and _refuse_or_handoff_exception(spec):
            obligation_applied = True
            hard_reasons = [
                "obligation_refuse_or_handoff:missing_execute_permission_still_applicable",
                *[f"waived:{r}" for r in hard_reasons],
            ]
        else:
            return {
                "case_id": case_id,
                "set_id": str(spec.get("set_id") or case_id),
                "decision": "not_applicable",
                "reasons": hard_reasons + advisory_reasons,
                "pack": str(spec.get("pack") or ""),
                "obligation_exception_applied": False,
            }

    reasons = hard_reasons + advisory_reasons
    if advisory_reasons and not hard_reasons:
        reasons = [
            "requires_satisfied_capability_unconfirmed",
            *advisory_reasons,
        ]
    return {
        "case_id": case_id,
        "set_id": str(spec.get("set_id") or case_id),
        "decision": "selected",
        "reasons": reasons or ["requires_satisfied"],
        "pack": str(spec.get("pack") or ""),
        "obligation_exception_applied": obligation_applied,
    }


def build_match_report(
    contract: Mapping[str, Any],
    case_specs: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Compile MatchReport for a list of case/set specs."""
    c = normalize_target_contract(contract)
    selected: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for spec in case_specs:
        row = match_case(c, spec)
        item = {
            "case_id": row["case_id"],
            "set_id": row["set_id"],
            "pack": row.get("pack"),
            "reasons": row.get("reasons") or [],
            "obligation_exception_applied": bool(row.get("obligation_exception_applied")),
        }
        if row.get("decision") == "selected":
            selected.append(item)
        else:
            excluded.append({**item, "status": "not_applicable"})

    return {
        "schema": MATCH_REPORT_SCHEMA,
        "target": {
            "object_type": c["object_type"],
            "object_id": c["object_id"],
            "object_version": c["object_version"],
        },
        "selected_cases": selected,
        "excluded_cases": excluded,
        "counts": {
            "selected": len(selected),
            "not_applicable": len(excluded),
            "total": len(selected) + len(excluded),
        },
        "phase": "p0_advisory",
        "honesty": (
            "MatchReport + Plan filter: missing_capability → not_applicable only when "
            "profile_source=explicit. derived_hints/unknown gaps are capability_unconfirmed "
            "and stay selected (suggest include; ≠ confirmed lack)."
        ),
    }


def match_eval_sets_for_target(
    contract: Mapping[str, Any],
    set_ids: Sequence[str],
    *,
    draft: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Match multiple builtin set_ids using applicability_draft defaults."""
    specs = [case_spec_for_set(sid, draft=draft) for sid in set_ids]
    report = build_match_report(contract, specs)
    report["draft_schema"] = str((draft or load_applicability_draft()).get("schema") or "")
    return report
