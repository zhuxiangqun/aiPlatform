"""Promote Subject capability seed banks → workspace freeze (claim=false).

Generalizes agent-only ``promote_agent_capability_bank`` for OBJECT_TYPES +
Subject-local banks. Stamps purpose_ok then draft→review→freeze via Case Pack
factory. Never opens accuracy_claim / certification.

Also provides seed-side ``stamp_subject_seed_purpose_ok`` (writes review into
``cases/*.json`` after content_purpose_ok; does **not** freeze pack.meta;
claim stays false).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

PROMOTE_SCHEMA = "eval.subject_capability_promote.v1"
SEED_PURPOSE_OK_SCHEMA = "eval.subject_seed_purpose_ok.v1"

_PURPOSE_OK_NOTE = (
    "Subject ordered promote: content_purpose_ok gate + owner sign-off path"
)
_SEED_PURPOSE_OK_NOTE = (
    "Seed purpose_ok after content_purpose_ok; pack.meta stays draft; "
    "claim/Certification closed until workspace freeze + independent claim gate"
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
        seed_dir: Callable[..., Path],
        object_type_member: bool,
    ) -> Dict[str, Any]:
        return {
            "pack_id": pack_id,
            "version": version,
            "profile_id": profile_id,
            "object_types": object_types,
            "validate": validate,
            "build": build,
            "seed_dir": seed_dir,
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
            seed_dir=prompt_bank.default_seed_dir,
            object_type_member=True,
        ),
        "workflow": _row(
            pack_id=wf_bank.PACK_ID,
            version=wf_bank.PACK_VERSION,
            profile_id=wf_bank.PROFILE_ID_REGRESSION,
            object_types=["workflow"],
            validate=wf_bank.validate_workflow_capability_bank,
            build=wf_bank.build_workflow_capability_cases,
            seed_dir=wf_bank.default_seed_dir,
            object_type_member=True,
        ),
        "model": _row(
            pack_id=model_bank.PACK_ID,
            version=model_bank.PACK_VERSION,
            profile_id=model_bank.PROFILE_ID_REGRESSION,
            object_types=["model"],
            validate=model_bank.validate_model_capability_bank,
            build=model_bank.build_model_capability_cases,
            seed_dir=model_bank.default_seed_dir,
            object_type_member=True,
        ),
        "skill": _row(
            pack_id=skill_bank.PACK_ID,
            version=skill_bank.PACK_VERSION,
            profile_id=skill_bank.PROFILE_ID_REGRESSION,
            object_types=["skill"],
            validate=skill_bank.validate_skill_capability_bank,
            build=skill_bank.build_skill_capability_cases,
            seed_dir=skill_bank.default_seed_dir,
            object_type_member=True,
        ),
        "api": _row(
            pack_id=api_bank.PACK_ID,
            version=api_bank.PACK_VERSION,
            profile_id=api_bank.PROFILE_ID_REGRESSION,
            object_types=["api"],
            validate=api_bank.validate_api_capability_bank,
            build=api_bank.build_api_capability_cases,
            seed_dir=api_bank.default_seed_dir,
            object_type_member=True,
        ),
        "generated_app": _row(
            pack_id=ga_bank.PACK_ID,
            version=ga_bank.PACK_VERSION,
            profile_id=ga_bank.PROFILE_ID_REGRESSION,
            object_types=["generated_app"],
            validate=ga_bank.validate_generated_app_capability_bank,
            build=ga_bank.build_generated_app_capability_cases,
            seed_dir=ga_bank.default_seed_dir,
            object_type_member=True,
        ),
        "dataset": _row(
            pack_id=ds_bank.PACK_ID,
            version=ds_bank.PACK_VERSION,
            profile_id=ds_bank.PROFILE_ID_REGRESSION,
            object_types=["dataset"],
            validate=ds_bank.validate_dataset_capability_bank,
            build=ds_bank.build_dataset_capability_cases,
            seed_dir=ds_bank.default_seed_dir,
            object_type_member=True,
        ),
        "system": _row(
            pack_id=system_bank.PACK_ID,
            version=system_bank.PACK_VERSION,
            profile_id=system_bank.PROFILE_ID_REGRESSION,
            object_types=["system"],
            validate=system_bank.validate_system_capability_bank,
            build=system_bank.build_system_capability_cases,
            seed_dir=system_bank.default_seed_dir,
            object_type_member=True,
        ),
        "kb": _row(
            pack_id=kb_bank.PACK_ID,
            version=kb_bank.PACK_VERSION,
            profile_id=kb_bank.PROFILE_ID_REGRESSION,
            object_types=["kb"],
            validate=kb_bank.validate_kb_capability_bank,
            build=kb_bank.build_kb_capability_cases,
            seed_dir=kb_bank.default_seed_dir,
            object_type_member=False,
        ),
        "code_review": _row(
            pack_id=cr_bank.PACK_ID,
            version=cr_bank.PACK_VERSION,
            profile_id=cr_bank.PROFILE_ID_REGRESSION,
            object_types=["code_review"],
            validate=cr_bank.validate_code_review_capability_bank,
            build=cr_bank.build_code_review_capability_cases,
            seed_dir=cr_bank.default_seed_dir,
            object_type_member=False,
        ),
        "session": _row(
            pack_id=session_bank.PACK_ID,
            version=session_bank.PACK_VERSION,
            profile_id=session_bank.PROFILE_ID_REGRESSION,
            object_types=["session"],
            validate=session_bank.validate_session_capability_bank,
            build=session_bank.build_session_capability_cases,
            seed_dir=session_bank.default_seed_dir,
            object_type_member=False,
        ),
        "tool": _row(
            pack_id=tool_bank.PACK_ID,
            version=tool_bank.PACK_VERSION,
            profile_id=tool_bank.PROFILE_ID_REGRESSION,
            object_types=["tool"],
            validate=tool_bank.validate_tool_capability_bank,
            build=tool_bank.build_tool_capability_cases,
            seed_dir=tool_bank.default_seed_dir,
            object_type_member=False,
        ),
        "multi_agent": _row(
            pack_id=ma_bank.PACK_ID,
            version=ma_bank.PACK_VERSION,
            profile_id=ma_bank.PROFILE_ID_REGRESSION,
            object_types=["multi_agent"],
            validate=ma_bank.validate_multi_agent_capability_bank,
            build=ma_bank.build_multi_agent_capability_cases,
            seed_dir=ma_bank.default_seed_dir,
            object_type_member=False,
        ),
    }


def list_promotable_subject_kinds() -> List[str]:
    return sorted(["agent", *_bank_specs().keys()])


def _stamp_review_purpose_ok_inplace(
    case: Mapping[str, Any], *, reviewer: str
) -> Dict[str, Any]:
    """Stamp purpose_ok on a seed case without Case Pack normalization."""
    c = dict(case)
    review = dict(c.get("review") or {})
    review.update(
        {
            "status": "purpose_ok",
            "decision": "purpose_ok",
            "reviewer": str(reviewer or "owner"),
            "notes": _SEED_PURPOSE_OK_NOTE,
        }
    )
    c["review"] = review
    return c


def stamp_subject_seed_purpose_ok(
    *,
    subject_kind: str,
    reviewer: str = "owner",
    seed_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate + content_purpose_ok → write purpose_ok into seed cases/*.json.

    Does **not** freeze pack.meta / workspace registry. claim_eligible stays
    false. Agent seeds are out of scope here (use promote_agent path).
    """
    from core.apps.eval.service.content_purpose_ok import (
        ContentPurposeOkError,
        assert_cases_content_purpose_ok,
    )
    from core.apps.eval.service.method_track import assert_not_subject_method

    kind = str(subject_kind or "").strip().lower()
    assert_not_subject_method(kind)
    if not kind:
        raise SubjectCapabilityPromoteError("subject_kind required")
    if kind == "agent":
        raise SubjectCapabilityPromoteError(
            "agent seed purpose_ok uses promote_agent_capability_bank / "
            "write_agent_capability_seeds — not stamp_subject_seed_purpose_ok"
        )

    specs = _bank_specs()
    spec = specs.get(kind)
    if spec is None:
        raise SubjectCapabilityPromoteError(f"no_promotable_subject:{kind}")

    report = spec["validate"](seed_dir=seed_dir) if seed_dir else spec["validate"]()
    if not report.get("ok"):
        raise SubjectCapabilityPromoteError(
            f"capability bank invalid: subject={kind} errors={report.get('errors')}"
        )

    raw_cases = (
        list(spec["build"](seed_dir=seed_dir))
        if seed_dir
        else list(spec["build"]())
    )
    try:
        content_report = assert_cases_content_purpose_ok(
            raw_cases, subject_kind=kind
        )
    except ContentPurposeOkError as exc:
        raise SubjectCapabilityPromoteError(str(exc)) from exc

    root = Path(seed_dir) if seed_dir else Path(spec["seed_dir"]())
    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        raise SubjectCapabilityPromoteError(f"cases dir missing: {cases_dir}")

    who = str(reviewer or "owner").strip() or "owner"
    stamped = 0
    files_touched = 0
    for path in sorted(cases_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SubjectCapabilityPromoteError(
                f"seed JSON invalid: {path}: {exc}"
            ) from exc
        if not isinstance(raw, list):
            raise SubjectCapabilityPromoteError(f"cases file must be a list: {path}")
        out_rows: List[Dict[str, Any]] = []
        changed = False
        for row in raw:
            if not isinstance(row, Mapping):
                raise SubjectCapabilityPromoteError(f"case must be object in {path}")
            prev = row.get("review") if isinstance(row.get("review"), Mapping) else {}
            stamped_row = _stamp_review_purpose_ok_inplace(row, reviewer=who)
            if dict(prev) != dict(stamped_row.get("review") or {}):
                changed = True
            out_rows.append(stamped_row)
            stamped += 1
        if changed:
            path.write_text(
                json.dumps(out_rows, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            files_touched += 1

    return {
        "schema": SEED_PURPOSE_OK_SCHEMA,
        "ok": True,
        "subject_kind": kind,
        "object_type_member": bool(spec["object_type_member"]),
        "pack_id": spec["pack_id"],
        "pack_version": spec["version"],
        "profile_id": spec["profile_id"],
        "seed_dir": str(root),
        "n_cases": stamped,
        "files_touched": files_touched,
        "reviewer": who,
        "content_purpose_ok": True,
        "content_purpose_ok_count": int(
            content_report.get("content_purpose_ok_count") or stamped
        ),
        "pack_status": "draft",
        "frozen": False,
        "claim_eligible": False,
        "accuracy_claim": False,
        "certification_eligible": False,
        "honesty": (
            f"seed cases/*.json stamped purpose_ok for {kind}; "
            "pack.meta remains draft; workspace freeze still required for "
            "profile_complete; claim/Certification stay closed"
        ),
    }


def stamp_all_subject_seed_purpose_ok(
    *, reviewer: str = "owner"
) -> Dict[str, Any]:
    """Stamp purpose_ok on every non-agent promotable Subject seed bank."""
    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for kind in sorted(_bank_specs().keys()):
        try:
            rows.append(
                stamp_subject_seed_purpose_ok(
                    subject_kind=kind, reviewer=reviewer
                )
            )
        except SubjectCapabilityPromoteError as exc:
            errors.append({"subject_kind": kind, "error": str(exc)})
    return {
        "schema": SEED_PURPOSE_OK_SCHEMA + ".inventory",
        "ok": not errors,
        "n_subjects": len(rows),
        "n_errors": len(errors),
        "subjects": rows,
        "errors": errors,
        "claim_eligible": False,
        "accuracy_claim": False,
        "certification_eligible": False,
        "honesty": (
            "Seed-side purpose_ok inventory only; does not freeze packs or "
            "open claim/Certification"
        ),
    }


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
        out["content_purpose_ok"] = bool(out.get("content_purpose_ok", True))
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
    from core.apps.eval.service.content_purpose_ok import (
        ContentPurposeOkError,
        assert_cases_content_purpose_ok,
    )

    raw_cases = list(spec["build"]())
    try:
        content_report = assert_cases_content_purpose_ok(
            raw_cases, subject_kind=kind
        )
    except ContentPurposeOkError as exc:
        raise SubjectCapabilityPromoteError(str(exc)) from exc
    cases = _stamp_purpose_ok(raw_cases, reviewer=who)

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
        "content_purpose_ok": True,
        "content_purpose_ok_count": int(
            content_report.get("content_purpose_ok_count") or len(cases)
        ),
        "honesty": (
            f"frozen curated {kind} bank from seed cases/*.json; "
            "claim_eligible=false; accuracy_claim closed; "
            "content_purpose_ok gated before purpose_ok stamp/freeze"
        ),
    }
