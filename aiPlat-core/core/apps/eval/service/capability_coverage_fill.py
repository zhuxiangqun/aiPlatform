"""P3 coverage-driven fill — gap analyze + reuse factory mutation/template.

Never freezes. Never opens claim_eligible / accuracy_claim.
Candidates stay draft and require human purpose_ok before freeze.
Subject-aware: in-scope catalog + seed bank follow Suite Profile Subject.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from core.apps.eval.service.capability_case_bank import (
    PACK_ID,
    PACK_VERSION,
    agent_regression_profile,
    build_agent_capability_cases,
)
from core.apps.eval.service.capability_id_map import (
    V1_IN_SCOPE,
    V1_OUT_OF_SCOPE,
    resolve_capability_id,
)
from core.apps.eval.service.case_factory import (
    CaseFactoryError,
    generate_cases_from_template,
)
from core.apps.eval.service.case_generation import CaseGenerationError, mutate_cases
from core.apps.eval.service.case_pack_ops import CasePackOpsError, expand_draft_workspace_pack

# Plan acceptance: Regression ≥5, Benchmark ≥8
DEFAULT_REGRESSION_MIN = 5
DEFAULT_BENCHMARK_MIN = 8

_log = logging.getLogger(__name__)


class CapabilityCoverageFillError(ValueError):
    """Coverage fill fail-closed."""


def subject_capability_scope(
    subject_kind: str = "agent",
) -> Tuple[Set[str], Set[str]]:
    """Return (in_scope, out_of_scope) capability ids for a Subject."""
    kind = str(subject_kind or "agent").strip().lower() or "agent"
    if kind == "agent":
        return set(V1_IN_SCOPE), set(V1_OUT_OF_SCOPE)
    from core.apps.eval.service.subject_adapter import get_subject_adapter

    adapter = get_subject_adapter(kind)
    caps = getattr(adapter, "v1_caps", None)
    if caps is not None:
        return set(caps), set()
    in_scope = {
        str(r.get("capability_id") or "").strip()
        for r in adapter.capability_catalog()
        if r.get("in_scope") and str(r.get("capability_id") or "").strip()
    }
    return in_scope, set()


def resolve_coverage_context(
    *,
    profile: Optional[Mapping[str, Any]] = None,
    profile_id: str = "",
    subject_kind: str = "",
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], str, Optional[Dict[str, Any]]]:
    """Resolve bank + Subject kind + normalized profile for coverage/fill."""
    from core.apps.eval.service.capability_case_bank import get_suite_profile
    from core.apps.eval.service.subject_suite_profiles import (
        SubjectSuiteProfileError,
        load_cases_for_suite_profile,
        normalize_suite_profile,
        resolve_subject_kind_from_profile,
    )

    prof: Optional[Dict[str, Any]] = dict(profile) if profile is not None else None
    pid = str(profile_id or "").strip()
    if prof is None and pid:
        try:
            prof = normalize_suite_profile(get_suite_profile(pid))
        except (ValueError, SubjectSuiteProfileError) as exc:
            _log.debug("coverage profile_id resolve failed %s: %s", pid, exc)
            prof = None
    elif prof is not None:
        try:
            prof = normalize_suite_profile(prof)
        except (ValueError, SubjectSuiteProfileError) as exc:
            _log.debug("coverage profile normalize failed: %s", exc)

    kind = str(subject_kind or "").strip().lower()
    if not kind and prof is not None:
        try:
            kind = resolve_subject_kind_from_profile(prof) or ""
        except Exception as exc:  # noqa: BLE001 — label fallback only
            _log.debug("subject_kind resolve fallback agent: %s", exc)
            kind = ""
    if not kind and pid and "." in pid:
        kind = pid.split(".", 1)[0].strip().lower()
    if not kind:
        kind = "agent"

    if cases is not None:
        bank = [dict(c) for c in cases if isinstance(c, Mapping)]
        return bank, kind, prof

    if prof is not None:
        try:
            bank = load_cases_for_suite_profile(prof)
            return bank, kind, prof
        except SubjectSuiteProfileError as exc:
            if kind == "agent" or (pid.startswith("agent.") if pid else False):
                return list(build_agent_capability_cases()), "agent", prof
            raise CapabilityCoverageFillError(str(exc)) from exc

    if kind == "agent":
        return list(build_agent_capability_cases()), kind, prof

    try:
        from core.apps.eval.service.subject_capability_promote import _bank_specs

        spec = _bank_specs().get(kind)
        if spec is None:
            raise CapabilityCoverageFillError(f"no_case_bank_for_subject:{kind}")
        return list(spec["build"]()), kind, prof
    except CapabilityCoverageFillError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CapabilityCoverageFillError(str(exc)) from exc


def _cap_of(case: Mapping[str, Any]) -> str:
    caps = case.get("capabilities") or []
    if caps:
        return resolve_capability_id(str(caps[0]), fail_closed=False)
    req = case.get("requires") if isinstance(case.get("requires"), Mapping) else {}
    rcaps = list(req.get("capabilities") or []) if isinstance(req, Mapping) else []
    if rcaps:
        return resolve_capability_id(str(rcaps[0]), fail_closed=False)
    return str(case.get("category") or "").strip().lower()


def _targets_from_profile(
    profile: Optional[Mapping[str, Any]],
    *,
    in_scope: Set[str],
    out_of_scope: Set[str],
    min_per_capability: Optional[int] = None,
) -> Dict[str, int]:
    """Resolve per-capability targets (quotas or flat minimum)."""
    scope = set(in_scope)
    if min_per_capability is not None:
        n = int(min_per_capability)
        if n < 1:
            raise CapabilityCoverageFillError("min_per_capability must be >= 1")
        return {cid: n for cid in sorted(scope)}

    prof = dict(profile or agent_regression_profile())
    quotas = prof.get("quotas") if isinstance(prof.get("quotas"), Mapping) else {}
    if not quotas:
        return {cid: DEFAULT_REGRESSION_MIN for cid in sorted(scope)}

    out: Dict[str, int] = {cid: 0 for cid in scope}
    for k, v in quotas.items():
        cid = resolve_capability_id(str(k), fail_closed=True)
        if cid in out_of_scope or cid not in scope:
            continue
        out[cid] = max(int(v), out.get(cid, 0))
    # Ensure every in-scope capability has at least regression floor when quota missing
    for cid in scope:
        if out.get(cid, 0) < 1:
            out[cid] = DEFAULT_REGRESSION_MIN
    return out


def analyze_capability_coverage(
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    *,
    profile: Optional[Mapping[str, Any]] = None,
    profile_id: str = "",
    subject_kind: str = "",
    min_per_capability: Optional[int] = None,
) -> Dict[str, Any]:
    """Per-capability have/need/gap vs Profile quotas or flat minimum."""
    rows, kind, prof = resolve_coverage_context(
        profile=profile,
        profile_id=profile_id,
        subject_kind=subject_kind,
        cases=cases,
    )
    in_scope, out_of_scope = subject_capability_scope(kind)
    targets = _targets_from_profile(
        prof,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        min_per_capability=min_per_capability,
    )
    counts: Counter = Counter()
    by_cap: Dict[str, List[str]] = defaultdict(list)
    for c in rows:
        cap = _cap_of(c)
        if not cap:
            continue
        try:
            cap = resolve_capability_id(cap, fail_closed=True)
        except Exception as exc:  # noqa: BLE001 — skip unknown cap ids
            _log.debug("skip unresolved capability id: %s", exc)
            continue
        if cap not in in_scope:
            continue
        counts[cap] += 1
        by_cap[cap].append(str(c.get("case_id") or ""))

    gaps: List[Dict[str, Any]] = []
    covered = 0
    for cid in sorted(in_scope):
        have = int(counts.get(cid, 0))
        need = int(targets.get(cid, DEFAULT_REGRESSION_MIN))
        gap = max(0, need - have)
        if gap == 0:
            covered += 1
        gaps.append(
            {
                "capability_id": cid,
                "have": have,
                "need": need,
                "gap": gap,
                "ok": gap == 0,
                "case_ids": by_cap.get(cid) or [],
            }
        )

    return {
        "ok": True,
        "schema": "eval.capability_coverage.v1",
        "subject_kind": kind,
        "case_count": len(rows),
        "in_scope": sorted(in_scope),
        "out_of_scope": sorted(out_of_scope),
        "targets": targets,
        "gaps": gaps,
        "n_gaps": sum(1 for g in gaps if g["gap"] > 0),
        "covered_capabilities": covered,
        "total_in_scope": len(in_scope),
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            f"coverage inventory / gap only (subject={kind}); "
            "not sufficiency; not an accuracy claim"
        ),
    }


def _stamp_candidate(
    case: Mapping[str, Any],
    *,
    capability: str,
    parent: Optional[Mapping[str, Any]] = None,
    method: str,
    subject_kind: str = "agent",
) -> Dict[str, Any]:
    """Ensure capability + draft review; copy test_purpose from parent when present."""
    kind = str(subject_kind or "agent").strip().lower() or "agent"
    out = dict(case)
    caps = [capability]
    out["capabilities"] = caps
    out["category"] = capability
    req = dict(out.get("requires") or {})
    req["capabilities"] = caps
    out["requires"] = req
    tags = list(out.get("tags") or [])
    for t in (kind, "coverage_fill", capability, method):
        if t not in tags:
            tags.append(t)
    out["tags"] = tags
    applies = dict(out.get("applies_to") or {})
    applies["object_types"] = [kind]
    out["applies_to"] = applies
    if parent and isinstance(parent.get("test_purpose"), Mapping):
        purpose = dict(parent["test_purpose"])
        purpose["summary"] = (
            f"[coverage_fill:{method}] " + str(purpose.get("summary") or "")
        ).strip()
        out["test_purpose"] = purpose
    review = dict(out.get("review") or {})
    review.update(
        {
            "status": "draft",
            "notes": (
                f"P3 coverage_fill via {method} ({kind}); "
                "needs purpose_ok before freeze"
            ),
        }
    )
    out["review"] = review
    return out


def generate_coverage_fill_candidates(
    *,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    profile: Optional[Mapping[str, Any]] = None,
    profile_id: str = "",
    subject_kind: str = "",
    min_per_capability: Optional[int] = None,
    method: str = "mutation",
    seed: str = "7",
    ops: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Generate draft candidates for each capability gap (mutation or template)."""
    method_l = str(method or "mutation").strip().lower() or "mutation"
    if method_l not in ("mutation", "template"):
        raise CapabilityCoverageFillError(
            f"method must be mutation|template, got {method!r}"
        )
    bank, kind, prof = resolve_coverage_context(
        profile=profile,
        profile_id=profile_id,
        subject_kind=subject_kind,
        cases=cases,
    )
    in_scope, _out = subject_capability_scope(kind)
    report = analyze_capability_coverage(
        bank,
        profile=prof,
        profile_id=profile_id,
        subject_kind=kind,
        min_per_capability=min_per_capability,
    )
    by_cap: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in bank:
        cap = _cap_of(c)
        if cap in in_scope:
            by_cap[cap].append(dict(c))

    candidates: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []
    for gap_row in report["gaps"]:
        gap = int(gap_row["gap"])
        if gap <= 0:
            continue
        cid = str(gap_row["capability_id"])
        seeds = list(by_cap.get(cid) or [])
        produced: List[Dict[str, Any]] = []
        if method_l == "mutation":
            if not seeds:
                plan.append(
                    {
                        "capability_id": cid,
                        "gap": gap,
                        "produced": 0,
                        "skipped": "no_seed_cases",
                    }
                )
                continue
            # Cycle seeds until we have enough mutations
            seed_batch = seeds[: max(1, min(len(seeds), gap))]
            try:
                mutated = mutate_cases(
                    seed_batch,
                    ops=list(ops or ["append_noise", "prefix_typo"]),
                    seed=f"{seed}:{cid}",
                    id_prefix=f"fill-{cid}",
                )
            except CaseGenerationError as e:
                raise CapabilityCoverageFillError(str(e)) from e
            for i, m in enumerate(mutated):
                if len(produced) >= gap:
                    break
                parent = seed_batch[i % len(seed_batch)]
                produced.append(
                    _stamp_candidate(
                        m,
                        capability=cid,
                        parent=parent,
                        method="mutation",
                        subject_kind=kind,
                    )
                )
        else:
            # template: one minimal lexical case per missing slot
            for i in range(gap):
                try:
                    rows = generate_cases_from_template(
                        {
                            "category": cid,
                            "rubric": {
                                "type": "lexical",
                                "must_contain": [cid.replace("_", " ")],
                            },
                            "prompt": (
                                f"[coverage_fill] Demonstrate {cid} behavior "
                                f"(slot {i + 1}). Refuse unsafe shortcuts."
                            ),
                            "capabilities": [cid],
                            "requires": {"capabilities": [cid]},
                            "applies_to": {"object_types": [kind]},
                            "tags": [kind, "coverage_fill", "template", cid],
                        },
                        variants=[
                            {
                                "case_id": f"fill-{cid}-tpl-{i + 1:03d}",
                                "seed": f"{seed}:{cid}:{i}",
                            }
                        ],
                    )
                except CaseFactoryError as e:
                    raise CapabilityCoverageFillError(str(e)) from e
                produced.append(
                    _stamp_candidate(
                        rows[0],
                        capability=cid,
                        method="template",
                        subject_kind=kind,
                    )
                )
        candidates.extend(produced)
        plan.append(
            {
                "capability_id": cid,
                "gap": gap,
                "produced": len(produced),
                "method": method_l,
            }
        )

    return {
        "ok": True,
        "subject_kind": kind,
        "method": method_l,
        "seed": seed,
        "coverage": report,
        "plan": plan,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            f"P3 draft candidates only (subject={kind}); "
            "reuse factory mutation/template; not gold; "
            "claim_eligible=false; purpose_ok required before freeze"
        ),
    }


def fill_capability_coverage(
    *,
    workspace_id: str,
    pack_id: str = PACK_ID,
    version: str = PACK_VERSION,
    caller_workspace_id: str = "",
    profile: Optional[Mapping[str, Any]] = None,
    profile_id: str = "",
    subject_kind: str = "",
    min_per_capability: Optional[int] = None,
    method: str = "mutation",
    seed: str = "7",
    ops: Optional[Sequence[str]] = None,
    apply: bool = False,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Analyze gaps → propose candidates → optionally expand non-frozen pack.

    ``apply=False`` (default): dry proposal only.
    ``apply=True``: expand_draft_workspace_pack with candidates (pack must be
    expandable; frozen packs fail closed — bump first).
    """
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CapabilityCoverageFillError("workspace_id required")

    proposal = generate_coverage_fill_candidates(
        cases=cases,
        profile=profile,
        profile_id=profile_id,
        subject_kind=subject_kind,
        min_per_capability=min_per_capability,
        method=method,
        seed=seed,
        ops=ops,
    )
    out: Dict[str, Any] = {
        "ok": True,
        "applied": False,
        "subject_kind": proposal.get("subject_kind"),
        "pack_id": str(pack_id or PACK_ID).strip() or PACK_ID,
        "version": str(version or PACK_VERSION).strip() or PACK_VERSION,
        "workspace_id": wid,
        "proposal": proposal,
        "n_candidates": proposal.get("n_candidates") or 0,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": proposal.get("honesty"),
    }
    if not apply:
        out["honesty"] = (
            "dry proposal only (apply=false); no pack mutation; claim closed"
        )
        return out

    cands = list(proposal.get("candidates") or [])
    if not cands:
        out["noop"] = True
        out["honesty"] = "no gaps / no candidates; nothing to apply"
        return out

    try:
        expanded = expand_draft_workspace_pack(
            pack_id=out["pack_id"],
            version=out["version"],
            workspace_id=wid,
            caller_workspace_id=str(caller_workspace_id or wid),
            cases=cands,
        )
    except CasePackOpsError as e:
        raise CapabilityCoverageFillError(str(e)) from e

    out["applied"] = True
    out["expand"] = expanded
    out["added"] = expanded.get("added")
    out["n_cases"] = expanded.get("n_cases")
    out["honesty"] = (
        "expanded draft with coverage_fill candidates; still claim_eligible=false; "
        "human purpose_ok + review required before freeze"
    )
    return out
