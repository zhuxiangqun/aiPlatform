"""Promote Subject capability seed banks → workspace freeze (claim=false).

Generalizes agent-only ``promote_agent_capability_bank`` for OBJECT_TYPES +
Subject-local banks. Stamps purpose_ok then draft→review→freeze via Case Pack
factory. Never opens accuracy_claim / certification.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

PROMOTE_SCHEMA = "eval.subject_capability_promote.v1"

_PURPOSE_OK_NOTE = (
    "Subject ordered promote: mechanical validate + owner sign-off path"
)


class SubjectCapabilityPromoteError(ValueError):
    """Promote failed (fail closed)."""


def _normalize_for_case_pack(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Map Subject seed case → Case Pack required fields (rubric/category/prompt)."""
    c = dict(raw)
    prompt = str(c.get("prompt") or c.get("user_input") or "").strip()
    if not prompt:
        raise SubjectCapabilityPromoteError(
            f"case {c.get('case_id')!r} missing prompt"
        )
    c["prompt"] = prompt

    caps = list(c.get("capabilities") or [])
    if not str(c.get("category") or "").strip():
        c["category"] = str(caps[0]).strip() if caps else "task_completion"

    rubric = c.get("rubric")
    if not isinstance(rubric, Mapping) or not rubric:
        crit = c.get("success_criteria")
        if isinstance(crit, Mapping) and crit:
            rubric = {
                "type": "lexical",
                "must_contain": list(crit.get("must_contain") or []),
                "must_not_contain": list(crit.get("must_not_contain") or []),
            }
        else:
            rubric = {"type": "lexical", "must_contain": [], "must_not_contain": []}
        c["rubric"] = dict(rubric)

    if not isinstance(c.get("provenance"), Mapping):
        applies = c.get("applies_to") if isinstance(c.get("applies_to"), Mapping) else {}
        ots = list(applies.get("object_types") or applies.get("subject_kinds") or [])
        c["provenance"] = {
            "source": "subject_capability_seed",
            "subject_kind": str(ots[0]) if ots else "subject",
        }
    return c


def _stamp_purpose_ok(
    cases: Sequence[Mapping[str, Any]], *, reviewer: str
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in cases:
        c = _normalize_for_case_pack(raw)
        review = dict(c.get("review") or {})
        review.update(
            {
                "status": "purpose_ok",
                "decision": "purpose_ok",
                "reviewer": str(reviewer or "owner"),
                "notes": _PURPOSE_OK_NOTE,
            }
        )
        c["review"] = review
        out.append(c)
    return out


def _bank_specs() -> Dict[str, Dict[str, Any]]:
    """subject_kind → validate/build/pack defaults (lazy imports)."""
    from core.apps.eval.service import (
        api_capability_bank as api_bank,
        code_review_capability_bank as cr_bank,
        dataset_capability_bank as ds_bank,
        generated_app_capability_bank as ga_bank,
        kb_capability_bank as kb_bank,
        model_capability_bank as model_bank,
        multi_agent_capability_bank as ma_bank,
        prompt_capability_bank as prompt_bank,
        session_capability_bank as session_bank,
        skill_capability_bank as skill_bank,
        system_capability_bank as system_bank,
        tool_capability_bank as tool_bank,
        workflow_capability_bank as wf_bank,
    )

    def _row(
        *,
        pack_id: str,
        version: str,
        profile_id: str,
        object_types: List[str],
        validate: Callable[..., Dict[str, Any]],
        build: Callable[..., List[Dict[str, Any]]],
        object_type_member: bool,
    ) -> Dict[str, Any]:
        return {
            "pack_id": pack_id,
            "version": version,
            "profile_id": profile_id,
            "object_types": object_types,
            "validate": validate,
            "build": build,
            "object_type_member": object_type_member,
        }

    return {
        "prompt": _row(
            pack_id=prompt_bank.PACK_ID,
            version=prompt_bank.PACK_VERSION,
            profile_id=prompt_bank.PROFILE_ID_REGRESSION,
            object_types=["prompt"],
            validate=prompt_bank.validate_prompt_capability_bank,
            build=prompt_bank.build_prompt_capability_cases,
            object_type_member=True,
        ),
        "workflow": _row(
            pack_id=wf_bank.PACK_ID,
            version=wf_bank.PACK_VERSION,
            profile_id=wf_bank.PROFILE_ID_REGRESSION,
            object_types=["workflow"],
            validate=wf_bank.validate_workflow_capability_bank,
            build=wf_bank.build_workflow_capability_cases,
            object_type_member=True,
        ),
        "model": _row(
            pack_id=model_bank.PACK_ID,
            version=model_bank.PACK_VERSION,
            profile_id=model_bank.PROFILE_ID_REGRESSION,
            object_types=["model"],
            validate=model_bank.validate_model_capability_bank,
            build=model_bank.build_model_capability_cases,
            object_type_member=True,
        ),
        "skill": _row(
            pack_id=skill_bank.PACK_ID,
            version=skill_bank.PACK_VERSION,
            profile_id=skill_bank.PROFILE_ID_REGRESSION,
            object_types=["skill"],
            validate=skill_bank.validate_skill_capability_bank,
            build=skill_bank.build_skill_capability_cases,
            object_type_member=True,
        ),
        "api": _row(
            pack_id=api_bank.PACK_ID,
            version=api_bank.PACK_VERSION,
            profile_id=api_bank.PROFILE_ID_REGRESSION,
            object_types=["api"],
            validate=api_bank.validate_api_capability_bank,
            build=api_bank.build_api_capability_cases,
            object_type_member=True,
        ),
        "generated_app": _row(
            pack_id=ga_bank.PACK_ID,
            version=ga_bank.PACK_VERSION,
            profile_id=ga_bank.PROFILE_ID_REGRESSION,
            object_types=["generated_app"],
            validate=ga_bank.validate_generated_app_capability_bank,
            build=ga_bank.build_generated_app_capability_cases,
            object_type_member=True,
        ),
        "dataset": _row(
            pack_id=ds_bank.PACK_ID,
            version=ds_bank.PACK_VERSION,
            profile_id=ds_bank.PROFILE_ID_REGRESSION,
            object_types=["dataset"],
            validate=ds_bank.validate_dataset_capability_bank,
            build=ds_bank.build_dataset_capability_cases,
            object_type_member=True,
        ),
        "system": _row(
            pack_id=system_bank.PACK_ID,
            version=system_bank.PACK_VERSION,
            profile_id=system_bank.PROFILE_ID_REGRESSION,
            object_types=["system"],
            validate=system_bank.validate_system_capability_bank,
            build=system_bank.build_system_capability_cases,
            object_type_member=True,
        ),
        "kb": _row(
            pack_id=kb_bank.PACK_ID,
            version=kb_bank.PACK_VERSION,
            profile_id=kb_bank.PROFILE_ID_REGRESSION,
            object_types=["kb"],
            validate=kb_bank.validate_kb_capability_bank,
            build=kb_bank.build_kb_capability_cases,
            object_type_member=False,
        ),
        "code_review": _row(
            pack_id=cr_bank.PACK_ID,
            version=cr_bank.PACK_VERSION,
            profile_id=cr_bank.PROFILE_ID_REGRESSION,
            object_types=["code_review"],
            validate=cr_bank.validate_code_review_capability_bank,
            build=cr_bank.build_code_review_capability_cases,
            object_type_member=False,
        ),
        "session": _row(
            pack_id=session_bank.PACK_ID,
            version=session_bank.PACK_VERSION,
            profile_id=session_bank.PROFILE_ID_REGRESSION,
            object_types=["session"],
            validate=session_bank.validate_session_capability_bank,
            build=session_bank.build_session_capability_cases,
            object_type_member=False,
        ),
        "tool": _row(
            pack_id=tool_bank.PACK_ID,
            version=tool_bank.PACK_VERSION,
            profile_id=tool_bank.PROFILE_ID_REGRESSION,
            object_types=["tool"],
            validate=tool_bank.validate_tool_capability_bank,
            build=tool_bank.build_tool_capability_cases,
            object_type_member=False,
        ),
        "multi_agent": _row(
            pack_id=ma_bank.PACK_ID,
            version=ma_bank.PACK_VERSION,
            profile_id=ma_bank.PROFILE_ID_REGRESSION,
            object_types=["multi_agent"],
            validate=ma_bank.validate_multi_agent_capability_bank,
            build=ma_bank.build_multi_agent_capability_cases,
            object_type_member=False,
        ),
    }


def list_promotable_subject_kinds() -> List[str]:
    return sorted(["agent", *_bank_specs().keys()])


def promote_subject_capability_bank(
    *,
    subject_kind: str,
    workspace_id: str,
    reviewer: str = "",
    frozen_by: str = "",
    pack_id: str = "",
    version: str = "",
    caller_workspace_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    """Validate seed bank → stamp purpose_ok → draft → approve → freeze.

    claim_eligible / accuracy_claim stay false. Agent delegates to existing
    ``promote_agent_capability_bank``.
    """
    from core.apps.eval.service.method_track import assert_not_subject_method

    kind = str(subject_kind or "").strip().lower()
    assert_not_subject_method(kind)
    if not kind:
        raise SubjectCapabilityPromoteError("subject_kind required")

    if kind == "agent":
        from core.apps.eval.service.capability_case_bank import (
            promote_agent_capability_bank,
        )

        out = promote_agent_capability_bank(
            workspace_id=workspace_id,
            reviewer=reviewer,
            frozen_by=frozen_by,
            pack_id=pack_id or "",
            version=version or "",
            caller_workspace_id=caller_workspace_id,
            notes=notes,
        )
        out = dict(out or {})
        out["schema"] = PROMOTE_SCHEMA
        out["subject_kind"] = "agent"
        out["claim_eligible"] = False
        out["accuracy_claim"] = False
        out["certification_eligible"] = False
        return out

    specs = _bank_specs()
    spec = specs.get(kind)
    if spec is None:
        raise SubjectCapabilityPromoteError(f"no_promotable_subject:{kind}")

    from core.apps.eval.service.case_factory import publish_draft_workspace_pack
    from core.apps.eval.service.case_freeze import CaseFreezeError, freeze_workspace_pack
    from core.apps.eval.service.case_pack_registry import PackRegistryError, get_pack_version
    from core.apps.eval.service.case_review_queue import (
        CaseReviewError,
        enqueue_pack_for_review,
        submit_review_decision,
    )

    wid = str(workspace_id or "").strip()
    if not wid:
        raise SubjectCapabilityPromoteError("workspace_id required")
    pid = str(pack_id or spec["pack_id"]).strip() or spec["pack_id"]
    ver = str(version or spec["version"]).strip() or spec["version"]
    who = str(reviewer or frozen_by or "owner").strip() or "owner"
    caller = str(caller_workspace_id or wid).strip() or wid

    report = spec["validate"]()
    if not report.get("ok"):
        raise SubjectCapabilityPromoteError(
            f"capability bank invalid: subject={kind} errors={report.get('errors')}"
        )
    cases = _stamp_purpose_ok(spec["build"](), reviewer=who)

    try:
        cur = get_pack_version(
            pack_id=pid,
            version=ver,
            scope="workspace",
            workspace_id=wid,
            caller_workspace_id=caller,
        )
        if (
            str(cur.get("kind") or "").lower() == "frozen"
            and str(cur.get("status") or "").lower() == "active"
        ):
            return {
                "schema": PROMOTE_SCHEMA,
                "ok": True,
                "noop": True,
                "subject_kind": kind,
                "object_type_member": bool(spec["object_type_member"]),
                "pack_id": pid,
                "version": ver,
                "kind": "frozen",
                "status": "active",
                "n_cases": report.get("case_count"),
                "profile_id": spec["profile_id"],
                "claim_eligible": False,
                "accuracy_claim": False,
                "certification_eligible": False,
                "honesty": "already frozen; claim_eligible=false",
            }
    except PackRegistryError:
        cur = None

    draft = publish_draft_workspace_pack(
        pack_id=pid,
        version=ver,
        cases=cases,
        workspace_id=wid,
        caller_workspace_id=caller,
        object_types=list(spec["object_types"]),
        kind="curated",
    )
    enqueue_pack_for_review(
        pack_id=pid,
        version=ver,
        workspace_id=wid,
        caller_workspace_id=caller,
        notes=str(notes or f"{kind} capability bank promote"),
    )
    submit_review_decision(
        pack_id=pid,
        version=ver,
        workspace_id=wid,
        decision="approve",
        reviewer=who,
        notes=f"purpose_ok ({kind} ordered promote)",
        caller_workspace_id=caller,
    )
    try:
        frozen = freeze_workspace_pack(
            pack_id=pid,
            version=ver,
            workspace_id=wid,
            caller_workspace_id=caller,
            frozen_by=str(frozen_by or who),
            notes=str(notes or f"{kind} capability freeze"),
        )
    except (CaseFreezeError, CaseReviewError) as exc:
        raise SubjectCapabilityPromoteError(str(exc)) from exc

    return {
        "schema": PROMOTE_SCHEMA,
        "ok": True,
        "noop": False,
        "subject_kind": kind,
        "object_type_member": bool(spec["object_type_member"]),
        "pack_id": pid,
        "version": ver,
        "kind": frozen.get("kind"),
        "status": frozen.get("status"),
        "pack_hash": frozen.get("pack_hash"),
        "n_cases": frozen.get("n_cases") or len(cases),
        "draft_hash": draft.get("pack_hash"),
        "profile_id": spec["profile_id"],
        "claim_eligible": False,
        "accuracy_claim": False,
        "certification_eligible": False,
        "reviewer": who,
        "honesty": (
            f"frozen curated {kind} bank from seed cases/*.json; "
            "claim_eligible=false; accuracy_claim closed; purpose_ok stamped before freeze"
        ),
    }
