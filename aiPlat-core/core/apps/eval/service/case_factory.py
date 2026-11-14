"""Case Pack factory — P1.0 draft path (template → validate → dedupe → register).

No LLM. claim_eligible stays false.
Human review: ``case_review_queue`` (P1.1). Freeze: ``case_freeze`` (P1.2).
Does not open accuracy_claim.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.case_pack_hash import compute_case_hash, compute_pack_hash
from core.apps.eval.service.case_pack_legacy import (
    ManifestValidationError,
    assert_claim_eligible_allowed,
    task_dict_to_case,
)
from core.apps.eval.service.case_pack_registry import (
    register_pack_version,
    write_pack_payload,
)


class CaseFactoryError(ValueError):
    """Case factory validation / publish failure."""


_REQUIRED_CASE_KEYS = ("case_id", "prompt", "rubric", "category")


def generate_cases_from_template(
    template: Mapping[str, Any],
    *,
    variants: Optional[Sequence[Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Deterministic template expansion (no LLM).

    Args:
        template: template 参数。
        variants: variants 参数。
    """
    base = dict(template or {})
    rows = list(variants or [{}])
    if not rows:
        rows = [{}]
    out: List[Dict[str, Any]] = []
    for i, var in enumerate(rows):
        if not isinstance(var, Mapping):
            raise CaseFactoryError(f"variant[{i}] must be object")
        merged = {**base, **dict(var)}
        if not merged.get("case_id"):
            stem = str(merged.get("id_stem") or base.get("case_id") or "case")
            merged["case_id"] = f"{stem}-{i+1:03d}"
        if not merged.get("prompt") and merged.get("user_input"):
            merged["prompt"] = merged.get("user_input")
        case = task_dict_to_case(merged, set_id=str(merged.get("set_id") or ""))
        # template provenance
        prov = dict(case.get("provenance") or {})
        prov["generator"] = "case_factory_template"
        prov["generator_version"] = "1"
        if "seed" in merged:
            prov["seed"] = merged.get("seed")
        case["provenance"] = prov
        case["review"] = {"status": "draft", "notes": ""}
        validate_case_dict(case)
        out.append(case)
    return out


def validate_case_dict(case: Mapping[str, Any]) -> None:
    """Fail closed if required Case Pack fields missing/empty.

    Args:
        case: case 参数。
    """
    if not isinstance(case, Mapping):
        raise CaseFactoryError("case must be object")
    for k in _REQUIRED_CASE_KEYS:
        v = case.get(k)
        if v is None or v == "" or v == {}:
            raise CaseFactoryError(f"case missing required field {k!r}")
    if not str(case.get("case_id") or "").strip():
        raise CaseFactoryError("case_id empty")
    # hash must be computable
    compute_case_hash(case)


def _content_dedupe_hash(case: Mapping[str, Any]) -> str:
    """Content fingerprint for factory dedupe: case_id excluded (auto-ids differ)."""
    payload = dict(case)
    payload["case_id"] = ""
    return compute_case_hash(payload)


def dedupe_cases_by_hash(
    cases: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep first case per content hash (stable by input order; ignores case_id).

    Args:
        cases: 用例列表。
    """
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for c in cases:
        validate_case_dict(c)
        h = _content_dedupe_hash(c)
        if h in seen:
            continue
        seen.add(h)
        out.append(dict(c))
    return out


def publish_draft_workspace_pack(
    *,
    pack_id: str,
    version: str,
    cases: Sequence[Mapping[str, Any]],
    workspace_id: str,
    caller_workspace_id: str = "",
    object_types: Optional[Sequence[str]] = None,
    kind: str = "curated",
) -> Dict[str, Any]:
    """Validate + dedupe + register workspace draft pack (claim_eligible=false).

    Args:
        pack_id: pack 标识。
        version: 版本号。
        cases: 用例列表。
        workspace_id: workspace 标识。
        caller_workspace_id: caller_workspace 标识。
        object_types: object_types 参数。
        kind: kind 参数。
    """
    wid = str(workspace_id or "").strip()
    if not wid:
        raise CaseFactoryError("workspace_id required for draft publish")
    k = str(kind or "curated").strip().lower() or "curated"
    if k in ("frozen",):
        raise CaseFactoryError("P1.0 factory cannot publish frozen packs — review/freeze later")
    assert_claim_eligible_allowed(kind=k, claim_eligible=False)
    cleaned = dedupe_cases_by_hash(cases)
    if not cleaned:
        raise CaseFactoryError("no cases to publish after dedupe")
    ots = list(object_types or ["agent"])
    pack_hash = compute_pack_hash(
        pack_id=str(pack_id).strip(),
        version=str(version).strip(),
        kind=k,
        claim_eligible=False,
        scope="workspace",
        object_types=ots,
        cases=cleaned,
    )
    pid = str(pack_id).strip()
    ver = str(version).strip()
    meta = register_pack_version(
        pack_id=pid,
        version=ver,
        kind=k,
        claim_eligible=False,
        scope="workspace",
        pack_hash=pack_hash,
        object_types=ots,
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
        status="draft",
    )
    write_pack_payload(
        pack_id=pid,
        version=ver,
        scope="workspace",
        cases=cleaned,
        meta={
            "kind": k,
            "claim_eligible": False,
            "hash": pack_hash,
            "object_types": ots,
            "status": "draft",
        },
        workspace_id=wid,
        caller_workspace_id=caller_workspace_id or wid,
    )
    return {
        "ok": True,
        "pack_id": pid,
        "version": ver,
        "pack_hash": pack_hash,
        "kind": k,
        "claim_eligible": False,
        "n_cases": len(cleaned),
        "case_ids": [c.get("case_id") for c in cleaned],
        "registry": meta,
        "accuracy_claim": False,
        "honesty": "draft curated pack; not frozen; accuracy_claim closed",
    }
