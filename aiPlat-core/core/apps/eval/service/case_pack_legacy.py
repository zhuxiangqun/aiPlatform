"""Legacy EvalSet/EvalTask ↔ Case Pack mapping + sample_manifest expand (P0).

Appendix A set_id→pack_id; nail 6 field map. Does not open accuracy_claim.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.apps.eval.service.case_pack_hash import (
    compute_case_hash,
    compute_pack_hash,
)

# Frozen Appendix A (eval-case-pack-factory.md §9)
LEGACY_SET_TO_PACK: Dict[str, Tuple[str, str]] = {
    "default/normal": ("agent.default.normal", "1.0.0"),
    "default/missing_info": ("agent.default.missing_info", "1.0.0"),
    "default/tool_failure": ("agent.default.tool_failure", "1.0.0"),
    "default/noise": ("agent.default.noise", "1.0.0"),
    "default/high_risk": ("agent.default.high_risk", "1.0.0"),
    "default/multi_turn": ("agent.default.multi_turn", "1.0.0"),
}

DEFAULT_PACK_VERSION = "1.0.0"


def pack_ref_for_set_id(set_id: str) -> Dict[str, str]:
    sid = str(set_id or "").strip()
    if sid in LEGACY_SET_TO_PACK:
        pack_id, version = LEGACY_SET_TO_PACK[sid]
        return {"pack_id": pack_id, "version": version}
    if "/" in sid:
        kind, stem = sid.split("/", 1)
        kind = kind.strip()
        stem = stem.strip()
        if kind in ("prompt", "workflow", "model", "dataset"):
            return {
                "pack_id": f"{kind}.{stem}",
                "version": DEFAULT_PACK_VERSION,
            }
    safe = sid.replace("/", ".")
    return {"pack_id": f"legacy.{safe}", "version": DEFAULT_PACK_VERSION}


def success_criteria_to_rubric(criteria: Any) -> Dict[str, Any]:
    if isinstance(criteria, Mapping) and criteria.get("type"):
        return dict(criteria)
    if isinstance(criteria, Mapping):
        return {"type": "lexical", **dict(criteria)}
    return {"type": "lexical"}


def rubric_to_success_criteria(rubric: Any) -> Dict[str, Any]:
    if not isinstance(rubric, Mapping):
        return {}
    out = dict(rubric)
    out.pop("type", None)
    return out


def task_dict_to_case(
    task: Mapping[str, Any],
    *,
    set_id: str = "",
    session_group: Optional[str] = None,
) -> Dict[str, Any]:
    """Map EvalTask-shaped dict → EvalCase-shaped dict (hash inputs)."""
    prompt = task.get("prompt")
    if prompt is None or prompt == "":
        prompt = task.get("user_input") or ""
    rubric = task.get("rubric")
    if not isinstance(rubric, Mapping):
        rubric = success_criteria_to_rubric(task.get("success_criteria"))
    category = str(task.get("category") or "normal")
    tags = task.get("tags")
    if not isinstance(tags, list) or not tags:
        tags = [category]
    sg = session_group
    if sg is None and set_id and "multi_turn" in set_id.replace("-", "_"):
        sg = set_id
    return {
        "case_id": str(task.get("case_id") or task.get("task_id") or ""),
        "prompt": str(prompt),
        "rubric": dict(rubric),
        "category": category,
        "tags": list(tags),
        "difficulty": str(task.get("difficulty") or "medium"),
        "applies_to": dict(task["applies_to"])
        if isinstance(task.get("applies_to"), Mapping)
        else {},
        "requires": dict(task["requires"])
        if isinstance(task.get("requires"), Mapping)
        else {},
        "oracle": dict(task["oracle"]) if isinstance(task.get("oracle"), Mapping) else {},
        "expected_tools": list(task.get("expected_tools") or []),
        "forbidden_tools": list(task.get("forbidden_tools") or []),
        "expected_steps": list(task.get("expected_steps") or []),
        "risk_level": str(task.get("risk_level") or "low"),
        "session_group": sg,
        "holdout": bool(task.get("holdout") or False),
        "provenance": {
            "generator": "legacy_eval_set",
            "generator_version": "1",
            "seed": None,
        },
        # Non-hash / projection fields
        "user_input": str(prompt),
        "success_criteria": rubric_to_success_criteria(rubric),
        "task_id": str(task.get("case_id") or task.get("task_id") or ""),
        "agent_id": str(task.get("agent_id") or ""),
        "set_id": set_id,
    }


def case_to_eval_task_dict(
    case: Mapping[str, Any], *, agent_id: str = ""
) -> Dict[str, Any]:
    prompt = case.get("prompt")
    if prompt is None or prompt == "":
        prompt = case.get("user_input") or ""
    rubric = case.get("rubric")
    if not isinstance(rubric, Mapping):
        rubric = success_criteria_to_rubric(case.get("success_criteria"))
    aid = str(agent_id or case.get("agent_id") or "")
    return {
        "task_id": str(case.get("case_id") or case.get("task_id") or ""),
        "agent_id": aid,
        "user_input": str(prompt),
        "category": str(case.get("category") or "normal"),
        "expected_tools": list(case.get("expected_tools") or []),
        "forbidden_tools": list(case.get("forbidden_tools") or []),
        "expected_steps": list(case.get("expected_steps") or []),
        "success_criteria": rubric_to_success_criteria(rubric),
        "risk_level": str(case.get("risk_level") or "low"),
    }


def load_set_tasks(set_id: str) -> List[Dict[str, Any]]:
    """Load tasks for a legacy set_id (builtin ensure + disk)."""
    from core.harness.evaluation.eval_runner import load_eval_set

    es = load_eval_set(set_id)
    if es is None:
        return []
    out: List[Dict[str, Any]] = []
    for t in es.tasks or []:
        out.append(
            {
                "task_id": t.task_id,
                "agent_id": t.agent_id,
                "user_input": t.user_input,
                "category": t.category,
                "expected_tools": list(t.expected_tools or []),
                "forbidden_tools": list(t.forbidden_tools or []),
                "expected_steps": list(t.expected_steps or []),
                "success_criteria": dict(t.success_criteria or {}),
                "risk_level": t.risk_level,
            }
        )
    return out


def expand_sets_to_manifest(
    set_ids: Sequence[str],
    *,
    claim_eligible: bool = False,
    scope: str = "global",
    kind: str = "frozen",
    object_types: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Expand selected legacy set_ids → sample_manifest + pack_refs + coverage.

    session_group: multi_turn sets share set_id as group (整组入选).
    """
    ots = list(object_types or ["agent"])
    manifest: List[Dict[str, Any]] = []
    pack_refs: List[Dict[str, Any]] = []
    coverage: Dict[str, Any] = {"sets": {}, "cases": 0}

    for sid in set_ids:
        sid = str(sid).strip()
        if not sid:
            continue
        ref = pack_ref_for_set_id(sid)
        tasks = load_set_tasks(sid)
        cases = [
            task_dict_to_case(t, set_id=sid, session_group=None) for t in tasks
        ]
        # multi_turn: force whole-set session_group
        if "multi_turn" in sid.replace("-", "_"):
            for c in cases:
                c["session_group"] = sid
        pack_hash = compute_pack_hash(
            pack_id=ref["pack_id"],
            version=ref["version"],
            kind=kind,
            claim_eligible=claim_eligible,
            scope=scope,
            object_types=ots,
            cases=cases,
        )
        pack_refs.append(
            {
                "pack_id": ref["pack_id"],
                "version": ref["version"],
                "hash": pack_hash,
                "set_id": sid,
                "kind": kind,
                "claim_eligible": bool(claim_eligible),
                "scope": scope,
            }
        )
        coverage["sets"][sid] = {
            "pack_id": ref["pack_id"],
            "n_cases": len(cases),
            "session_group": sid if "multi_turn" in sid.replace("-", "_") else None,
        }
        for c in cases:
            h = compute_case_hash(c)
            manifest.append(
                {
                    "case_id": c["case_id"],
                    "hash": h,
                    "pack_id": ref["pack_id"],
                    "pack_version": ref["version"],
                    "session_group": c.get("session_group"),
                    "set_id": sid,
                }
            )
            coverage["cases"] = int(coverage["cases"]) + 1

    manifest.sort(key=lambda r: str(r.get("case_id") or ""))
    return manifest, pack_refs, coverage


class ClaimEligibilityError(ValueError):
    """generated/exploratory packs cannot be claim_eligible."""


def assert_claim_eligible_allowed(*, kind: str, claim_eligible: bool) -> None:
    """CI/runtime guard: generated + claim_eligible=true is rejected."""
    k = str(kind or "").strip().lower()
    if bool(claim_eligible) and k in ("generated", "trace", "exploratory"):
        raise ClaimEligibilityError(
            f"claim_eligible=true forbidden for kind={k!r}"
        )


class ManifestValidationError(ValueError):
    """Fail-closed: Plan v2 must not execute without a valid sample_manifest."""


def require_sample_manifest(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Runner entry: only sample_manifest is executable (nail 2).

    v1 plans: synthesize from selected_cases set_ids (migration expand).
    v2 plans: empty/missing → fail closed (no full-pack fallback).
    """
    schema = str(plan.get("schema") or "")
    raw = plan.get("sample_manifest")
    if isinstance(raw, list) and raw:
        return [dict(x) for x in raw if isinstance(x, Mapping)]

    if schema.endswith(".v2") or schema == "eval.evaluation_plan.v2":
        raise ManifestValidationError(
            "sample_manifest missing or empty — fail closed (no full-pack fallback)"
        )

    # v1 / unknown: expand selected set_ids once for migration callers
    selected = plan.get("selected_cases") or []
    set_ids = []
    for row in selected:
        if isinstance(row, Mapping):
            sid = str(row.get("set_id") or row.get("case_id") or "").strip()
            if sid:
                set_ids.append(sid)
    if not set_ids:
        raise ManifestValidationError("no selected_cases to expand into sample_manifest")
    manifest, _, _ = expand_sets_to_manifest(set_ids)
    if not manifest:
        raise ManifestValidationError("expanded sample_manifest empty — fail closed")
    return manifest
