"""P1.4 Case Pack ops — expand draft, version++ bump, coverage summary.

Honesty: claim_eligible stays false; frozen packs are immutable (bump → new draft).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_factory import (
    CaseFactoryError,
    dedupe_cases_by_hash,
    generate_cases_from_template,
)
from core.apps.eval.service.case_pack_hash import compute_pack_hash
from core.apps.eval.service.case_pack_legacy import assert_claim_eligible_allowed
from core.apps.eval.service.case_pack_registry import (
    PackRegistryError,
    assert_pack_acl,
    get_pack_version,
    load_pack_payload,
    load_registry,
    register_pack_version,
    update_pack_version_meta,
    write_pack_payload,
)

_EXPANDABLE_STATUSES = frozenset({"draft", "in_review", "rejected"})


class CasePackOpsError(ValueError):
    """Pack expand / bump / coverage failure."""


def _semver_bump_patch(version: str) -> str:
    ver = str(version or "").strip() or "0.1.0"
    parts = ver.split(".")
    if len(parts) >= 3 and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    if len(parts) == 2 and parts[-1].isdigit():
        return f"{parts[0]}.{int(parts[1]) + 1}.0"
    if ver.isdigit():
        return str(int(ver) + 1)
    return f"{ver}.1"


def expand_draft_workspace_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    template: Optional[Mapping[str, Any]] = None,
    variants: Optional[Sequence[Mapping[str, Any]]] = None,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Append cases into a non-frozen draft/in_review/rejected pack (dedupe)."""
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CasePackOpsError("workspace_id required")
    pid = str(pack_id).strip()
    ver = str(version).strip()
    try:
        cur = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    st = str(cur.get("status") or "").lower()
    kind = str(cur.get("kind") or "").lower()
    if kind == "frozen":
        raise CasePackOpsError(
            "frozen pack immutable — use bump_workspace_pack_version (version++)"
        )
    if st not in _EXPANDABLE_STATUSES:
        raise CasePackOpsError(
            f"expand requires status in {sorted(_EXPANDABLE_STATUSES)}, got {st!r}"
        )

    try:
        payload = load_pack_payload(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    existing = list(payload.get("cases") or [])
    extra: List[Dict[str, Any]] = []
    if cases is not None:
        extra.extend(dict(c) for c in cases)
    elif template is not None or variants is not None:
        try:
            extra.extend(
                generate_cases_from_template(
                    dict(template or {}),
                    variants=list(variants or [{}]),
                )
            )
        except CaseFactoryError as e:
            raise CasePackOpsError(str(e)) from e
    else:
        raise CasePackOpsError("cases or template/variants required")

    before_n = len(existing)
    merged = dedupe_cases_by_hash([*existing, *extra])
    added = len(merged) - before_n
    if added <= 0 and len(merged) == before_n:
        return {
            "ok": True,
            "pack_id": pid,
            "version": ver,
            "n_cases": before_n,
            "added": 0,
            "noop": True,
            "pack_hash": cur.get("hash"),
            "claim_eligible": False,
            "accuracy_claim": False,
            "honesty": "no new cases after dedupe; claim closed",
        }

    ots = list(cur.get("object_types") or ["agent"])
    k = kind or "curated"
    assert_claim_eligible_allowed(kind=k, claim_eligible=False)
    new_hash = compute_pack_hash(
        pack_id=pid,
        version=ver,
        kind=k,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=merged,
    )
    try:
        meta = update_pack_version_meta(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
            pack_hash=new_hash,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    write_pack_payload(
        pack_id=pid,
        version=ver,
        scope="workspace",
        cases=merged,
        meta={
            "kind": k,
            "claim_eligible": False,
            "hash": new_hash,
            "object_types": ots,
            "status": st,
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "n_cases": len(merged),
        "added": max(0, len(merged) - before_n),
        "pack_hash": new_hash,
        "prior_hash": cur.get("hash"),
        "registry": meta,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "expanded non-frozen pack; claim_eligible=false",
    }


def bump_workspace_pack_version(
    *,
    pack_id: str,
    from_version: str,
    workspace_id: str,
    to_version: str = "",
    extra_cases: Optional[Sequence[Mapping[str, Any]]] = None,
    template: Optional[Mapping[str, Any]] = None,
    variants: Optional[Sequence[Mapping[str, Any]]] = None,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """version++: copy cases into a new draft curated pack (never mutates frozen)."""
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CasePackOpsError("workspace_id required")
    pid = str(pack_id).strip()
    src_ver = str(from_version).strip()
    try:
        src = get_pack_version(
            pack_id=pid,
            version=src_ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
        payload = load_pack_payload(
            pack_id=pid,
            version=src_ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    cases = [dict(c) for c in (payload.get("cases") or [])]
    if extra_cases:
        cases.extend(dict(c) for c in extra_cases)
    if template is not None or variants is not None:
        try:
            cases.extend(
                generate_cases_from_template(
                    dict(template or {}),
                    variants=list(variants or [{}]),
                )
            )
        except CaseFactoryError as e:
            raise CasePackOpsError(str(e)) from e
    cleaned = dedupe_cases_by_hash(cases)
    if not cleaned:
        raise CasePackOpsError("no cases to bump after dedupe")

    new_ver = str(to_version or "").strip() or _semver_bump_patch(src_ver)
    if new_ver == src_ver:
        raise CasePackOpsError("to_version must differ from from_version")

    ots = list(src.get("object_types") or ["agent"])
    # New lineage always starts as curated draft (even if source was frozen).
    kind = "curated"
    assert_claim_eligible_allowed(kind=kind, claim_eligible=False)
    pack_hash = compute_pack_hash(
        pack_id=pid,
        version=new_ver,
        kind=kind,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=cleaned,
    )
    try:
        meta = register_pack_version(
            pack_id=pid,
            version=new_ver,
            kind=kind,
            claim_eligible=False,
            scope="workspace",
            pack_hash=pack_hash,
            object_types=ots,
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
            status="draft",
        )
    except PackRegistryError as e:
        raise CasePackOpsError(str(e)) from e

    write_pack_payload(
        pack_id=pid,
        version=new_ver,
        scope="workspace",
        cases=cleaned,
        meta={
            "kind": kind,
            "claim_eligible": False,
            "hash": pack_hash,
            "object_types": ots,
            "status": "draft",
            "bumped_from": src_ver,
            "source_kind": src.get("kind"),
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "from_version": src_ver,
        "version": new_ver,
        "kind": kind,
        "status": "draft",
        "n_cases": len(cleaned),
        "pack_hash": pack_hash,
        "registry": meta,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            "version++ creates draft curated; source frozen untouched; "
            "claim_eligible=false"
        ),
    }


def summarize_workspace_pack_coverage(
    *,
    workspace_id: str,
    caller_workspace_id: str = "",
) -> Dict[str, Any]:
    """Coverage summary for workspace packs (status/kind counts + per-version rows)."""
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CasePackOpsError("workspace_id required")
    assert_pack_acl(
        scope="workspace",
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        write=False,
    )
    reg = load_registry(scope="workspace", workspace_id=wid)
    items: List[Dict[str, Any]] = []
    by_status: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    for pid, entry in (reg.get("packs") or {}).items():
        if not isinstance(entry, dict):
            continue
        for ver, meta in (entry.get("versions") or {}).items():
            if not isinstance(meta, dict):
                continue
            st = str(meta.get("status") or "").lower() or "unknown"
            kind = str(meta.get("kind") or "").lower() or "unknown"
            by_status[st] = by_status.get(st, 0) + 1
            by_kind[kind] = by_kind.get(kind, 0) + 1
            n_cases = None
            try:
                payload = load_pack_payload(
                    pack_id=pid,
                    version=ver,
                    scope="workspace",
                    workspace_id=wid,
                    caller_workspace_id=caller_workspace_id or wid,
                )
                n_cases = len(payload.get("cases") or [])
            except PackRegistryError:
                n_cases = None
            items.append(
                {
                    "pack_id": pid,
                    "version": ver,
                    "status": st,
                    "kind": kind,
                    "claim_eligible": bool(meta.get("claim_eligible")),
                    "hash": meta.get("hash"),
                    "n_cases": n_cases,
                }
            )
    items.sort(key=lambda r: (r["pack_id"], r["version"]))
    return {
        "ok": True,
        "workspace_id": wid,
        "n_versions": len(items),
        "by_status": by_status,
        "by_kind": by_kind,
        "items": items,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": "coverage inventory only; not an accuracy claim",
    }
