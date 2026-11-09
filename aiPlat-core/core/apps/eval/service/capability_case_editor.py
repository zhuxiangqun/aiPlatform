"""Capability Case Editor — browse seeds + maintain workspace draft cases.

Repo seeds (cases/*.json) stay content authority for git. UI edits **workspace**
draft packs only; frozen packs require bump. claim_eligible stays false.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.capability_case_bank import (
    PACK_ID,
    PACK_VERSION,
    build_agent_capability_cases,
    validate_capability_case,
)
from core.apps.eval.service.capability_id_map import V1_IN_SCOPE, resolve_capability_ids
from core.apps.eval.service.case_factory import (
    CaseFactoryError,
    publish_draft_workspace_pack,
    validate_case_dict,
)
from core.apps.eval.service.case_pack_hash import compute_case_hash, compute_pack_hash
from core.apps.eval.service.case_pack_legacy import assert_claim_eligible_allowed
from core.apps.eval.service.case_pack_ops import CasePackOpsError, bump_workspace_pack_version
from core.apps.eval.service.case_pack_registry import (
    PackRegistryError,
    get_pack_version,
    load_pack_payload,
    update_pack_version_meta,
    write_pack_payload,
)

_EDITABLE = frozenset({"draft", "in_review", "rejected"})


class CapabilityCaseEditorError(ValueError):
    """Case editor fail-closed."""


def _cap_of(case: Mapping[str, Any]) -> str:
    caps = case.get("capabilities") or []
    if caps:
        try:
            return resolve_capability_id_safe(str(caps[0]))
        except Exception:
            return str(caps[0]).strip().lower()
    return str(case.get("category") or "").strip().lower()


def resolve_capability_id_safe(raw: str) -> str:
    return resolve_capability_ids([raw], fail_closed=True)[0]


def _case_summary(case: Mapping[str, Any]) -> Dict[str, Any]:
    purpose = case.get("test_purpose") if isinstance(case.get("test_purpose"), Mapping) else {}
    review = case.get("review") if isinstance(case.get("review"), Mapping) else {}
    return {
        "case_id": str(case.get("case_id") or ""),
        "capability_id": _cap_of(case),
        "prompt_preview": str(case.get("prompt") or "")[:160],
        "difficulty": case.get("difficulty"),
        "risk_level": case.get("risk_level"),
        "review_status": review.get("status"),
        "purpose_summary": str(purpose.get("summary") or "")[:160],
        "holdout": bool(case.get("holdout")),
    }


def list_seed_capability_cases(
    *,
    capability_id: str = "",
) -> Dict[str, Any]:
    """Read-only browse of repo seed bank (not workspace)."""
    rows = build_agent_capability_cases()
    cap = str(capability_id or "").strip()
    if cap:
        cid = resolve_capability_id_safe(cap)
        rows = [c for c in rows if _cap_of(c) == cid]
    return {
        "ok": True,
        "source": "seed",
        "editable": False,
        "pack_id": PACK_ID,
        "version": PACK_VERSION,
        "n_cases": len(rows),
        "cases": [_case_summary(c) for c in rows],
        "claim_eligible": False,
        "honesty": "repo seed browse only; edit via workspace draft pack",
    }


def get_seed_capability_case(*, case_id: str) -> Dict[str, Any]:
    cid = str(case_id or "").strip()
    if not cid:
        raise CapabilityCaseEditorError("case_id required")
    for c in build_agent_capability_cases():
        if str(c.get("case_id") or "") == cid:
            return {
                "ok": True,
                "source": "seed",
                "editable": False,
                "case": dict(c),
                "claim_eligible": False,
            }
    raise CapabilityCaseEditorError(f"seed case not found: {cid}")


def _load_workspace_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    caller_workspace_id: str = "",
) -> tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CapabilityCaseEditorError("workspace_id required")
    pid = str(pack_id or PACK_ID).strip() or PACK_ID
    ver = str(version or PACK_VERSION).strip() or PACK_VERSION
    caller = str(caller_workspace_id or wid).strip() or wid
    try:
        meta = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller,
        )
        payload = load_pack_payload(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller,
        )
    except PackRegistryError as e:
        raise CapabilityCaseEditorError(str(e)) from e
    cases = [dict(c) for c in (payload.get("cases") or []) if isinstance(c, Mapping)]
    return meta, payload, cases


def list_workspace_pack_cases(
    *,
    workspace_id: str,
    pack_id: str = PACK_ID,
    version: str = PACK_VERSION,
    capability_id: str = "",
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    meta, _payload, cases = _load_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id,
    )
    cap = str(capability_id or "").strip()
    if cap:
        cid = resolve_capability_id_safe(cap)
        cases = [c for c in cases if _cap_of(c) == cid]
    kind = str(meta.get("kind") or "").lower()
    status = str(meta.get("status") or "").lower()
    editable = kind != "frozen" and status in _EDITABLE
    return {
        "ok": True,
        "source": "workspace",
        "pack_id": str(pack_id or PACK_ID).strip() or PACK_ID,
        "version": str(version or PACK_VERSION).strip() or PACK_VERSION,
        "kind": kind,
        "status": status,
        "editable": editable,
        "n_cases": len(cases),
        "cases": [_case_summary(c) for c in cases],
        "claim_eligible": False,
        "honesty": (
            "workspace pack list; edit only when draft/in_review/rejected; "
            "frozen → bump first"
        ),
    }


def get_workspace_pack_case(
    *,
    workspace_id: str,
    case_id: str,
    pack_id: str = PACK_ID,
    version: str = PACK_VERSION,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    cid = str(case_id or "").strip()
    if not cid:
        raise CapabilityCaseEditorError("case_id required")
    meta, _payload, cases = _load_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id,
    )
    kind = str(meta.get("kind") or "").lower()
    status = str(meta.get("status") or "").lower()
    editable = kind != "frozen" and status in _EDITABLE
    for c in cases:
        if str(c.get("case_id") or "") == cid:
            return {
                "ok": True,
                "source": "workspace",
                "pack_id": str(pack_id or PACK_ID).strip() or PACK_ID,
                "version": str(version or PACK_VERSION).strip() or PACK_VERSION,
                "kind": kind,
                "status": status,
                "editable": editable,
                "case": c,
                "claim_eligible": False,
            }
    raise CapabilityCaseEditorError(f"case not found: {cid}")


def _normalize_editor_case(raw: Mapping[str, Any]) -> Dict[str, Any]:
    case = dict(raw)
    caps = resolve_capability_ids(
        list(case.get("capabilities") or ([case.get("category")] if case.get("category") else [])),
        fail_closed=True,
    )
    if not caps:
        raise CapabilityCaseEditorError("capabilities / category required")
    if caps[0] not in V1_IN_SCOPE:
        raise CapabilityCaseEditorError(
            f"out-of-scope capability {caps[0]!r} (A3–A5/A8/A9 stay unknown)"
        )
    case["capabilities"] = caps
    case["category"] = caps[0]
    req = dict(case.get("requires") or {})
    req["capabilities"] = caps
    case["requires"] = req
    case.setdefault("object_types", ["agent"])
    applies = dict(case.get("applies_to") or {})
    applies.setdefault("object_types", ["agent"])
    case["applies_to"] = applies
    case.setdefault("oracle", {"type": "lexical"})
    case.setdefault("expected_tools", [])
    case.setdefault("forbidden_tools", [])
    case.setdefault("expected_steps", [])
    case.setdefault("holdout", False)
    case.setdefault("session_group", None)
    case.setdefault("difficulty", "medium")
    case.setdefault("risk_level", "low")
    tags = list(case.get("tags") or [])
    for t in ("agent", caps[0], "case_editor"):
        if t not in tags:
            tags.append(t)
    case["tags"] = tags
    review = dict(case.get("review") or {})
    review.setdefault("status", "draft")
    review["notes"] = str(
        review.get("notes") or "edited via capability case editor UI"
    )
    case["review"] = review
    prov = dict(case.get("provenance") or {})
    prov["generator"] = prov.get("generator") or "capability_case_editor"
    prov["generator_version"] = "1"
    case["provenance"] = prov
    if not isinstance(case.get("rubric"), Mapping):
        raise CapabilityCaseEditorError("rubric object required")
    if not isinstance(case.get("test_purpose"), Mapping):
        raise CapabilityCaseEditorError("test_purpose object required")
    case["hash"] = compute_case_hash(case)
    try:
        validate_case_dict(case)
    except CaseFactoryError as e:
        raise CapabilityCaseEditorError(str(e)) from e
    errs = validate_capability_case(case)
    if errs:
        raise CapabilityCaseEditorError("; ".join(errs))
    return case


def _rewrite_cases(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    caller_workspace_id: str,
    meta: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    wid = str(workspace_id).strip()
    caller = str(caller_workspace_id or wid).strip() or wid
    pid = str(pack_id).strip()
    ver = str(version).strip()
    kind = str(meta.get("kind") or "curated").lower() or "curated"
    status = str(meta.get("status") or "draft").lower()
    if kind == "frozen":
        raise CapabilityCaseEditorError(
            "frozen pack immutable — bump version first"
        )
    if status not in _EDITABLE:
        raise CapabilityCaseEditorError(
            f"edit requires status in {sorted(_EDITABLE)}, got {status!r}"
        )
    ots = list(meta.get("object_types") or ["agent"])
    rows = [dict(c) for c in cases]
    assert_claim_eligible_allowed(kind=kind, claim_eligible=False)
    new_hash = compute_pack_hash(
        pack_id=pid,
        version=ver,
        kind=kind,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=rows,
    )
    try:
        reg = update_pack_version_meta(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller,
            pack_hash=new_hash,
        )
    except PackRegistryError as e:
        raise CapabilityCaseEditorError(str(e)) from e
    write_pack_payload(
        pack_id=pid,
        version=ver,
        scope="workspace",
        cases=rows,
        meta={
            "kind": kind,
            "claim_eligible": False,
            "hash": new_hash,
            "object_types": ots,
            "status": status,
        },
        workspace_id=wid,
        caller_workspace_id=caller,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "n_cases": len(rows),
        "pack_hash": new_hash,
        "registry": reg,
        "editable": True,
        "claim_eligible": False,
        "accuracy_claim": False,
    }


def upsert_workspace_pack_case(
    *,
    workspace_id: str,
    case: Mapping[str, Any],
    pack_id: str = PACK_ID,
    version: str = PACK_VERSION,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Create or replace one case in an editable workspace pack."""
    if not isinstance(case, Mapping):
        raise CapabilityCaseEditorError("case must be object")
    normalized = _normalize_editor_case(case)
    cid = str(normalized.get("case_id") or "").strip()
    meta, _payload, cases = _load_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id,
    )
    replaced = False
    out_cases: List[Dict[str, Any]] = []
    for c in cases:
        if str(c.get("case_id") or "") == cid:
            out_cases.append(normalized)
            replaced = True
        else:
            out_cases.append(c)
    if not replaced:
        out_cases.append(normalized)
    result = _rewrite_cases(
        pack_id=str(pack_id or PACK_ID).strip() or PACK_ID,
        version=str(version or PACK_VERSION).strip() or PACK_VERSION,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        meta=meta,
        cases=out_cases,
    )
    result["case_id"] = cid
    result["replaced"] = replaced
    result["created"] = not replaced
    result["honesty"] = (
        "upserted workspace draft case; claim_eligible=false; "
        "purpose_ok / freeze still required for release"
    )
    return result


def delete_workspace_pack_case(
    *,
    workspace_id: str,
    case_id: str,
    pack_id: str = PACK_ID,
    version: str = PACK_VERSION,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    cid = str(case_id or "").strip()
    if not cid:
        raise CapabilityCaseEditorError("case_id required")
    meta, _payload, cases = _load_workspace_pack(
        pack_id=pack_id,
        version=version,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id,
    )
    kept = [c for c in cases if str(c.get("case_id") or "") != cid]
    if len(kept) == len(cases):
        raise CapabilityCaseEditorError(f"case not found: {cid}")
    result = _rewrite_cases(
        pack_id=str(pack_id or PACK_ID).strip() or PACK_ID,
        version=str(version or PACK_VERSION).strip() or PACK_VERSION,
        workspace_id=workspace_id,
        caller_workspace_id=caller_workspace_id or workspace_id,
        meta=meta,
        cases=kept,
    )
    result["case_id"] = cid
    result["deleted"] = True
    result["honesty"] = "deleted from editable workspace pack; claim closed"
    return result


def open_capability_bank_editor(
    *,
    workspace_id: str,
    pack_id: str = PACK_ID,
    version: str = PACK_VERSION,
    caller_workspace_id: str = "",
    bump_if_frozen: bool = True,
) -> Dict[str, Any]:
    """Ensure an editable workspace pack exists (seed → draft, or bump frozen)."""
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CapabilityCaseEditorError("workspace_id required")
    pid = str(pack_id or PACK_ID).strip() or PACK_ID
    ver = str(version or PACK_VERSION).strip() or PACK_VERSION
    caller = str(caller_workspace_id or wid).strip() or wid

    try:
        meta, _payload, cases = _load_workspace_pack(
            pack_id=pid,
            version=ver,
            workspace_id=wid,
            caller_workspace_id=caller,
        )
    except CapabilityCaseEditorError:
        # Missing → publish seed bank as draft.
        seed = build_agent_capability_cases()
        try:
            draft = publish_draft_workspace_pack(
                pack_id=pid,
                version=ver,
                cases=seed,
                workspace_id=wid,
                caller_workspace_id=caller,
                object_types=["agent"],
                kind="curated",
            )
        except CaseFactoryError as e:
            raise CapabilityCaseEditorError(str(e)) from e
        return {
            "ok": True,
            "action": "published_seed_draft",
            "pack_id": pid,
            "version": ver,
            "n_cases": draft.get("n_cases") or len(seed),
            "editable": True,
            "kind": "curated",
            "status": "draft",
            "pack_hash": draft.get("pack_hash"),
            "claim_eligible": False,
            "honesty": (
                "created workspace draft from repo seeds; "
                "edits stay in workspace until freeze/bump"
            ),
        }

    kind = str(meta.get("kind") or "").lower()
    status = str(meta.get("status") or "").lower()
    if kind != "frozen" and status in _EDITABLE:
        return {
            "ok": True,
            "action": "existing_editable",
            "pack_id": pid,
            "version": ver,
            "n_cases": len(cases),
            "editable": True,
            "kind": kind,
            "status": status,
            "pack_hash": meta.get("hash"),
            "claim_eligible": False,
            "honesty": "reusing editable workspace pack",
        }

    if kind == "frozen" and bump_if_frozen:
        try:
            bumped = bump_workspace_pack_version(
                pack_id=pid,
                from_version=ver,
                workspace_id=wid,
                caller_workspace_id=caller,
            )
        except CasePackOpsError as e:
            raise CapabilityCaseEditorError(str(e)) from e
        return {
            "ok": True,
            "action": "bumped_frozen",
            "pack_id": pid,
            "from_version": ver,
            "version": bumped.get("version"),
            "n_cases": bumped.get("n_cases"),
            "editable": True,
            "kind": "curated",
            "status": "draft",
            "pack_hash": bumped.get("pack_hash"),
            "claim_eligible": False,
            "honesty": (
                "frozen immutable — opened new draft via version++; "
                "claim_eligible=false"
            ),
        }

    return {
        "ok": True,
        "action": "not_editable",
        "pack_id": pid,
        "version": ver,
        "n_cases": len(cases),
        "editable": False,
        "kind": kind,
        "status": status,
        "pack_hash": meta.get("hash"),
        "claim_eligible": False,
        "honesty": "pack not editable; bump or reset status first",
    }
