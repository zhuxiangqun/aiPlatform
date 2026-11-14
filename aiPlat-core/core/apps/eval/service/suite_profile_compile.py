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
    get_suite_profile,
)
from core.apps.eval.service.capability_id_map import (
    V1_IN_SCOPE,
    V1_OUT_OF_SCOPE,
    resolve_capability_id,
)
from core.apps.eval.service.case_generation import apply_holdout_flags, partition_holdout
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
    OBJECT_TYPES,
    build_agent_target_contract,
    build_target_contract,
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
    """Apply fixed quotas; return selected cases + selection meta.

    Args:
        cases: 用例列表。
        profile: profile 参数。
    """
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


def _purpose_for_profile(profile_id: str) -> List[str]:
    pid = str(profile_id or "").lower()
    if "smoke" in pid:
        return ["behavior", "smoke"]
    if "benchmark" in pid:
        return ["behavior", "benchmark"]
    return ["behavior", "regression"]


def apply_profile_holdout(
    selected: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Split selected into eval vs holdout per profile.holdout.

    Args:
        selected: selected 参数。
        profile: profile 参数。
    """
    hold = profile.get("holdout") if isinstance(profile.get("holdout"), Mapping) else {}
    enabled = bool(hold.get("enabled"))
    rows = [dict(c) for c in selected]
    if not enabled:
        return rows, [], {
            "enabled": False,
            "exclude_from_tuning": True,
            "n_eval": len(rows),
            "n_holdout": 0,
            "ratio": 0.0,
        }
    try:
        ratio = float(hold.get("ratio") if hold.get("ratio") is not None else 0.2)
    except (TypeError, ValueError) as e:
        raise SuiteProfileCompileError(f"holdout.ratio invalid: {hold.get('ratio')!r}") from e
    if ratio <= 0 or ratio > 0.5:
        raise SuiteProfileCompileError(
            f"holdout.ratio must be in (0, 0.5], got {ratio}"
        )
    seed = hold.get("seed")
    if seed is None:
        seed = profile.get("seed")
    marked = apply_holdout_flags(
        rows,
        ratio=ratio,
        seed=str(seed if seed is not None else 0),
        holdout=True,
    )
    parts = partition_holdout(marked)
    exclude = bool(hold.get("exclude_from_tuning", True))
    eval_cases = list(parts["eval"]) if exclude else marked
    holdout_cases = list(parts["holdout"]) if exclude else []
    meta = {
        "enabled": True,
        "ratio": ratio,
        "seed": seed,
        "exclude_from_tuning": exclude,
        "n_eval": len(eval_cases),
        "n_holdout": len(parts["holdout"]),
        "holdout_case_ids": [str(c.get("case_id") or "") for c in parts["holdout"]],
    }
    return eval_cases, holdout_cases, meta


def _manifest_rows(
    cases: Sequence[Mapping[str, Any]],
    *,
    pack_id: str,
    pack_version: str,
    holdout: bool = False,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for c in cases:
        rows.append(
            {
                "case_id": str(c.get("case_id") or ""),
                "hash": compute_case_hash(c),
                "set_id": str(c.get("category") or _cap_of(c) or ""),
                "pack_id": pack_id,
                "pack_version": pack_version,
                "session_group": c.get("session_group"),
                "category": str(c.get("category") or _cap_of(c) or ""),
                "capability_id": _cap_of(c),
                "holdout": bool(holdout or c.get("holdout")),
            }
        )
    return rows


def _resolve_suite_profile(
    *,
    profile: Optional[Mapping[str, Any]],
    profile_id: str,
) -> Dict[str, Any]:
    from core.apps.eval.service.subject_suite_profiles import normalize_suite_profile

    if profile is not None:
        return normalize_suite_profile(dict(profile))
    pid = str(profile_id or "").strip()
    if not pid:
        return normalize_suite_profile(agent_regression_profile(), subject_kind="agent")
    try:
        # get_suite_profile already resolves agent + Subject seed profiles.
        return normalize_suite_profile(get_suite_profile(pid))
    except ValueError as e:
        raise SuiteProfileCompileError(str(e)) from e


def _build_profile_target_contract(
    *,
    subject_kind: str,
    object_id: str,
    object_version: str,
    capabilities: Sequence[str],
    purpose: Sequence[str],
) -> Dict[str, Any]:
    kind = str(subject_kind or "agent").strip().lower() or "agent"
    caps = list(capabilities)
    eval_profile = {
        "profile_source": "explicit",
        "capabilities": caps,
        "eval_purpose": list(purpose),
    }
    if kind == "agent":
        return normalize_target_contract(
            build_agent_target_contract(
                object_id=object_id,
                object_version=object_version,
                capabilities=caps,
                eval_profile=eval_profile,
            )
        )
    if kind in OBJECT_TYPES:
        return build_target_contract(
            object_type=kind,
            object_id=object_id,
            object_version=object_version,
            capabilities=caps,
            eval_purpose=list(purpose),
            target_runtime=["fixture"],
            boundaries={
                "claim_eligible": False,
                "subject_kind": kind,
                "accuracy_claim": False,
            },
        )
    # Subject-local (kb/session/tool/…): adapter disclosure, not OBJECT_TYPES contract.
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    adapter = get_subject_adapter(kind)
    raw = adapter.build_contract(
        object_id=object_id,
        object_version=object_version,
        capabilities=caps,
        eval_profile=eval_profile,
    )
    out = dict(raw or {})
    out["claim_eligible"] = False
    out.setdefault("subject_kind", kind)
    out.setdefault("object_type_registered", False)
    out.setdefault(
        "honesty",
        f"{kind} Subject-local contract; not OBJECT_TYPES; claim closed",
    )
    return out


def compile_plan_from_suite_profile(
    *,
    profile: Optional[Mapping[str, Any]] = None,
    profile_id: str = "",
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    object_id: str = "",
    object_version: str = "0.1.0",
    require_content_purpose_ok: bool = True,
) -> Dict[str, Any]:
    """Compile Plan v2 whose sample_manifest is the Profile-selected case list.

    Args:
        profile: profile 参数。
        profile_id: profile 标识。
        cases: 用例列表。
        object_id: object 标识。
        object_version: object_version 参数。
        require_content_purpose_ok: require_content_purpose_ok 参数。
    """
    from core.apps.eval.service.subject_suite_profiles import (
        SubjectSuiteProfileError,
        load_cases_for_suite_profile,
        resolve_subject_kind_from_profile,
    )

    prof = _resolve_suite_profile(profile=profile, profile_id=profile_id)

    if str(prof.get("schema") or "") != PROFILE_SCHEMA:
        if str(prof.get("profile_id") or "") != PROFILE_ID and not prof.get("quotas"):
            raise SuiteProfileCompileError("invalid suite profile")
        prof.setdefault("schema", PROFILE_SCHEMA)

    subject_kind = resolve_subject_kind_from_profile(prof) or "agent"
    if cases is not None:
        bank = list(cases)
    else:
        try:
            bank = load_cases_for_suite_profile(prof)
        except SubjectSuiteProfileError as exc:
            if subject_kind == "agent":
                bank = build_agent_capability_cases()
            else:
                raise SuiteProfileCompileError(str(exc)) from exc

    if require_content_purpose_ok:
        from core.apps.eval.service.content_purpose_ok import (
            ContentPurposeOkError,
            assert_cases_content_purpose_ok,
        )

        try:
            assert_cases_content_purpose_ok(bank, subject_kind=subject_kind)
        except ContentPurposeOkError as exc:
            raise SuiteProfileCompileError(str(exc)) from exc

    selected, selection_meta = select_cases_for_profile(bank, prof)
    eval_cases, holdout_cases, holdout_meta = apply_profile_holdout(selected, prof)

    pack_id = str(prof.get("pack_id") or PACK_ID)
    pack_version = str(prof.get("pack_version") or PACK_VERSION)
    pid = str(prof.get("profile_id") or PROFILE_ID)
    purpose = _purpose_for_profile(pid)
    oid = (
        str(object_id or "").strip()
        or f"{subject_kind}.capability.target"
    )
    ots = [subject_kind] if subject_kind in OBJECT_TYPES else []
    pack_hash = compute_pack_hash(
        pack_id=pack_id,
        version=pack_version,
        kind="frozen",
        claim_eligible=False,
        scope=str(prof.get("pack_scope") or "global"),
        object_types=ots,
        cases=eval_cases,
    )

    sample_manifest = _manifest_rows(
        eval_cases, pack_id=pack_id, pack_version=pack_version, holdout=False
    )
    holdout_manifest = _manifest_rows(
        holdout_cases, pack_id=pack_id, pack_version=pack_version, holdout=True
    )

    caps = sorted({_cap_of(c) for c in eval_cases if _cap_of(c)})
    contract = _build_profile_target_contract(
        subject_kind=subject_kind,
        object_id=oid,
        object_version=object_version,
        capabilities=caps,
        purpose=purpose,
    )

    selection = {
        "strategy": selection_meta.get("strategy"),
        "seed": selection_meta.get("seed"),
        "sample_n": len(sample_manifest),
        "quota_trace": selection_meta.get("quota_trace") or [],
        "degraded": bool(selection_meta.get("degraded")),
        "degraded_reasons": [],
        "profile_id": pid,
        "holdout": holdout_meta,
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
            "profile_id": pid,
        }
    ]
    plan_id = compute_plan_id_v2(
        contract=contract,
        purpose=purpose,
        selection=selection,
        pack_refs=pack_refs,
        manifest_hash=manifest_hash,
        plan_schema=PLAN_SCHEMA_V2,
    )
    execution_fingerprint = compute_execution_fingerprint(
        plan_id=plan_id,
        manifest_hash=manifest_hash,
        runner_id="suite_profile_compile",
        run_key=pid,
    )

    coverage = {
        "cases": len(selected),
        "manifest_cases_after_sample": len(sample_manifest),
        "holdout_cases": len(holdout_cases),
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
        "profile_id": pid,
        "subject_kind": subject_kind,
        "object_type_member": subject_kind in OBJECT_TYPES,
        "content_purpose_ok": bool(require_content_purpose_ok),
        "suite_profile": {
            "schema": prof.get("schema"),
            "profile_id": pid,
            "subject_kind": subject_kind,
            "pack_id": pack_id,
            "pack_version": pack_version,
            "quotas": prof.get("quotas"),
            "strategy": prof.get("strategy"),
            "seed": prof.get("seed"),
            "holdout": holdout_meta,
            "claim_eligible": False,
        },
        "target_contract": contract,
        "purpose": purpose,
        "selected_cases": [
            {
                "set_id": str(c.get("category") or _cap_of(c)),
                "case_id": c.get("case_id"),
                "pack": "capability",
                "status": "selected",
                "reasons": ["profile_quota"],
            }
            for c in eval_cases
        ],
        "excluded_cases": [
            {
                "case_id": c.get("case_id"),
                "status": "holdout",
                "reasons": ["profile_holdout"],
            }
            for c in holdout_cases
        ],
        "selection": selection,
        "pack_ref": pack_refs[0],
        "pack_refs": pack_refs,
        "sample_manifest": sample_manifest,
        "holdout_manifest": holdout_manifest,
        "manifest_hash": manifest_hash,
        "execution_fingerprint": execution_fingerprint,
        "coverage": coverage,
        "claims_policy": claims_policy_stub(thin=False, profile_source="explicit"),
        "claim_eligible": False,
        "accuracy_claim": False,
        "counts": {
            "selected": len(eval_cases),
            "manifest_cases": len(sample_manifest),
            "holdout": len(holdout_cases),
            "excluded": len(holdout_cases),
            "total": len(selected),
        },
        "honesty": (
            f"Plan v2 from Suite Profile ({subject_kind}): sample_manifest is sole "
            "execution list; holdout disclosed when enabled; "
            "content_purpose_ok gated when require_content_purpose_ok; "
            "claim_eligible=false; accuracy_claim closed; quotas fixed (v1)."
        ),
    }
