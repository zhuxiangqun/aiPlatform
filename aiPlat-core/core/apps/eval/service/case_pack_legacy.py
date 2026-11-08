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


class ClaimEligibilityError(ValueError):
    """generated/exploratory packs cannot be claim_eligible."""


class ManifestValidationError(ValueError):
    """Fail-closed: Plan v2 must not execute without a valid sample_manifest."""


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
    """Load raw task dicts for a legacy set_id (user overlay or engine).

    Prefer ``~/.aiplat/eval_sets`` after ``ensure_builtin_sets`` (never overwrites
    user-modified files). Fall back to engine templates when disk load fails.
    Reads JSON directly so typed extras (e.g. ``fixture_table``) are preserved.
    """
    import json
    from pathlib import Path

    from core.harness.evaluation.eval_runner import ensure_builtin_sets, _eval_dir

    sid = str(set_id or "").strip()
    if not sid:
        return []
    ensure_builtin_sets()
    candidates: List[Path] = [_eval_dir() / f"{sid}.json"]
    engine = Path(__file__).resolve().parents[3] / "engine" / "eval_sets"
    if "/" in sid:
        kind, stem = sid.split("/", 1)
        if kind == "default":
            candidates.append(engine / f"{stem}.json")
        else:
            candidates.append(engine / kind / f"{stem}.json")
    else:
        candidates.append(engine / f"{sid}.json")

    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if not isinstance(tasks, list):
            continue
        return [dict(t) for t in tasks if isinstance(t, dict)]
    return []


def _sync_pack_ref_with_registry(
    *,
    pack_id: str,
    version: str,
    pack_hash: str,
    kind: str,
    claim_eligible: bool,
    scope: str,
    object_types: Sequence[str],
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
) -> None:
    """Workspace/tenant: register or verify hash. Global: verify only if already registered."""
    from core.apps.eval.service.case_pack_registry import (
        PackRegistryError,
        get_pack_version,
        load_registry,
        register_pack_version,
    )

    sc = str(scope or "global").strip().lower()
    if sc == "workspace" and workspace_id:
        try:
            register_pack_version(
                pack_id=pack_id,
                version=version,
                kind=kind,
                claim_eligible=claim_eligible,
                scope=sc,
                pack_hash=pack_hash,
                object_types=list(object_types),
                workspace_id=workspace_id,
                caller_workspace_id=caller_workspace_id or workspace_id,
            )
            return
        except PackRegistryError as e:
            if "already registered" not in str(e):
                raise
            existing = get_pack_version(
                pack_id=pack_id,
                version=version,
                scope=sc,
                workspace_id=workspace_id,
                caller_workspace_id=caller_workspace_id or workspace_id,
            )
            if str(existing.get("hash") or "") != pack_hash:
                raise ManifestValidationError(
                    f"registry hash mismatch pack={pack_id}@{version}: "
                    f"registry={existing.get('hash')} live={pack_hash}"
                ) from e
            return
    if sc == "tenant" and tenant_id:
        try:
            register_pack_version(
                pack_id=pack_id,
                version=version,
                kind=kind,
                claim_eligible=claim_eligible,
                scope=sc,
                pack_hash=pack_hash,
                object_types=list(object_types),
                tenant_id=tenant_id,
                caller_tenant_id=caller_tenant_id or tenant_id,
            )
            return
        except PackRegistryError as e:
            if "already registered" not in str(e):
                raise
            existing = get_pack_version(
                pack_id=pack_id,
                version=version,
                scope=sc,
                tenant_id=tenant_id,
                caller_tenant_id=caller_tenant_id or tenant_id,
            )
            if str(existing.get("hash") or "") != pack_hash:
                raise ManifestValidationError(
                    f"registry hash mismatch pack={pack_id}@{version}: "
                    f"registry={existing.get('hash')} live={pack_hash}"
                ) from e
            return
    # global / unread registry: verify if entry exists; never write in P0
    try:
        reg = load_registry(scope=sc)
    except PackRegistryError:
        return
    packs = reg.get("packs") or {}
    entry = packs.get(pack_id)
    if not isinstance(entry, dict):
        return
    versions = entry.get("versions") or {}
    if version not in versions:
        return
    existing = get_pack_version(
        pack_id=pack_id,
        version=version,
        scope=sc,
    )
    if str(existing.get("hash") or "") != pack_hash:
        raise ManifestValidationError(
            f"registry hash mismatch pack={pack_id}@{version}: "
            f"registry={existing.get('hash')} live={pack_hash}"
        )


def expand_sets_to_manifest(
    set_ids: Sequence[str],
    *,
    claim_eligible: bool = False,
    scope: str = "global",
    kind: str = "frozen",
    object_types: Optional[Sequence[str]] = None,
    workspace_id: str = "",
    tenant_id: str = "",
    caller_workspace_id: str = "",
    caller_tenant_id: str = "",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Expand selected legacy set_ids → sample_manifest + pack_refs + coverage.

    session_group: multi_turn sets share set_id as group (整组入选).
    Workspace/tenant scopes sync pack_refs into the scoped registry (nail 5).
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
        _sync_pack_ref_with_registry(
            pack_id=ref["pack_id"],
            version=ref["version"],
            pack_hash=pack_hash,
            kind=kind,
            claim_eligible=claim_eligible,
            scope=scope,
            object_types=ots,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            caller_workspace_id=caller_workspace_id,
            caller_tenant_id=caller_tenant_id,
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


def assert_claim_eligible_allowed(*, kind: str, claim_eligible: bool) -> None:
    """CI/runtime guard: generated + claim_eligible=true is rejected."""
    k = str(kind or "").strip().lower()
    if bool(claim_eligible) and k in ("generated", "trace", "exploratory"):
        raise ClaimEligibilityError(
            f"claim_eligible=true forbidden for kind={k!r}"
        )


def verify_manifest_case_hashes(
    manifest: Sequence[Mapping[str, Any]],
) -> None:
    """Fail closed if any manifest case hash ≠ live canonical hash (nail 2/4).

    Reloads tasks by ``set_id`` (legacy path). Missing set/case → fail closed.
    Does **not** fall back to running the full pack.
    """
    by_set: Dict[str, List[Mapping[str, Any]]] = {}
    for row in manifest:
        if not isinstance(row, Mapping):
            continue
        sid = str(row.get("set_id") or "").strip()
        if not sid:
            raise ManifestValidationError(
                "manifest row missing set_id — fail closed (cannot verify hash)"
            )
        by_set.setdefault(sid, []).append(row)

    for sid, rows in by_set.items():
        tasks = load_set_tasks(sid)
        by_id = {
            str(t.get("case_id") or t.get("task_id") or ""): t for t in tasks
        }
        for row in rows:
            cid = str(row.get("case_id") or "").strip()
            expected = str(row.get("hash") or "").strip()
            if not cid or not expected:
                raise ManifestValidationError(
                    f"manifest row incomplete for set={sid!r} — fail closed"
                )
            raw = by_id.get(cid)
            if raw is None:
                raise ManifestValidationError(
                    f"case_id={cid!r} not in set={sid!r} — fail closed"
                )
            case = task_dict_to_case(
                raw,
                set_id=sid,
                session_group=row.get("session_group"),
            )
            if "multi_turn" in sid.replace("-", "_"):
                case["session_group"] = sid
            live = compute_case_hash(case)
            if live != expected:
                raise ManifestValidationError(
                    f"case hash mismatch case_id={cid!r} set={sid!r}: "
                    f"manifest={expected} live={live} — fail closed"
                )


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
