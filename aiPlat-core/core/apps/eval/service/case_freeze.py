"""P1.2 Case Pack freeze — reviewed → kind=frozen (claim_eligible stays false).

In-place case edits forbidden after freeze; version++ is the only evolution path.
Does not open accuracy_claim.
"""
from __future__ import annotations

from typing import Any, Dict

from core.apps.eval.service.case_pack_hash import compute_pack_hash
from core.apps.eval.service.case_pack_legacy import assert_claim_eligible_allowed
from core.apps.eval.service.case_pack_registry import (
    PackRegistryError,
    freeze_pack_version,
    get_pack_version,
    load_pack_payload,
    write_pack_payload,
)


class CaseFreezeError(ValueError):
    """Freeze path failure."""


def freeze_workspace_pack(
    *,
    pack_id: str,
    version: str,
    workspace_id: str,
    caller_workspace_id: str = "",
    frozen_by: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Freeze a reviewed workspace pack. claim_eligible forced false.

    Args:
        pack_id: pack 标识。
        version: 版本号。
        workspace_id: workspace 标识。
        caller_workspace_id: caller_workspace 标识。
        frozen_by: frozen_by 参数。
        notes: notes 参数。
    """
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CaseFreezeError("workspace_id required")
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
        raise CaseFreezeError(str(e)) from e

    st = str(cur.get("status") or "").lower()
    kind = str(cur.get("kind") or "").lower()
    if kind == "frozen" and st == "active":
        return {
            "ok": True,
            "pack_id": pid,
            "version": ver,
            "kind": "frozen",
            "status": "active",
            "pack_hash": cur.get("hash"),
            "claim_eligible": False,
            "noop": True,
            "accuracy_claim": False,
            "honesty": "already frozen; claim_eligible=false; accuracy_claim closed",
        }
    if st != "reviewed":
        raise CaseFreezeError(
            f"freeze requires status=reviewed, got {st!r}"
        )
    if kind in ("generated", "trace", "exploratory"):
        raise CaseFreezeError(f"cannot freeze kind={kind!r}")

    try:
        payload = load_pack_payload(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
        )
    except PackRegistryError as e:
        raise CaseFreezeError(str(e)) from e

    cases = payload.get("cases") or []
    if not isinstance(cases, list) or not cases:
        raise CaseFreezeError("pack payload has no cases — fail closed")
    ots = list(cur.get("object_types") or ["agent"])
    assert_claim_eligible_allowed(kind="frozen", claim_eligible=False)
    new_hash = compute_pack_hash(
        pack_id=pid,
        version=ver,
        kind="frozen",
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=cases,
    )
    try:
        meta = freeze_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            pack_hash=new_hash,
            workspace_id=wid,
            caller_workspace_id=caller_workspace_id or wid,
            frozen_by=frozen_by,
            notes=notes,
        )
    except PackRegistryError as e:
        raise CaseFreezeError(str(e)) from e

    write_pack_payload(
        pack_id=pid,
        version=ver,
        scope="workspace",
        cases=cases,
        meta={
            "kind": "frozen",
            "claim_eligible": False,
            "hash": new_hash,
            "object_types": ots,
            "status": "active",
            "review": meta.get("review") or {},
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "kind": "frozen",
        "status": "active",
        "pack_hash": new_hash,
        "prior_hash": cur.get("hash"),
        "n_cases": len(cases),
        "registry": meta,
        "claim_eligible": False,
        "accuracy_claim": False,
        "honesty": (
            "frozen≠claim; claim_eligible=false; accuracy_claim closed; "
            "in-place edits forbidden — version++ only"
        ),
    }
