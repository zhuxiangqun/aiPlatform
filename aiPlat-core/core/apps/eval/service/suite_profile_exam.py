"""Suite Profile exam — execute only ``sample_manifest`` (ADR nail 2).

Runs capability-bank cases referenced by a Profile-compiled Plan v2.
Dry = deterministic lexical fixture; live = LLM + lexical oracle.
Never opens claim_eligible / accuracy_claim.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.apps.eval.service.capability_case_bank import build_agent_capability_cases
from core.apps.eval.service.case_pack_hash import (
    compute_case_hash,
    compute_execution_fingerprint,
)
from core.apps.eval.service.case_pack_legacy import (
    ManifestValidationError,
    require_sample_manifest,
    rubric_to_success_criteria,
)
from core.apps.eval.service.eval_plan import attach_evaluation_plan
from core.apps.eval.service.suite_profile_compile import compile_plan_from_suite_profile
from core.apps.eval.service.typed_plan_exam import (
    dry_stub_output,
    live_llm_output,
    score_lexical_output,
)

_log = logging.getLogger(__name__)


class SuiteProfileExamError(ValueError):
    """Suite profile exam fail-closed."""


def index_cases_by_id(
    cases: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for c in cases:
        if not isinstance(c, Mapping):
            continue
        cid = str(c.get("case_id") or "").strip()
        if cid:
            out[cid] = dict(c)
    return out


def verify_capability_manifest_hashes(
    manifest: Sequence[Mapping[str, Any]],
    cases_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    """Fail closed if manifest hash ≠ bank case canonical hash."""
    if not manifest:
        raise ManifestValidationError("sample_manifest empty — fail closed")
    for i, row in enumerate(manifest):
        if not isinstance(row, Mapping):
            raise ManifestValidationError(f"manifest[{i}] must be object")
        cid = str(row.get("case_id") or "").strip()
        if not cid:
            raise ManifestValidationError(f"manifest[{i}] missing case_id")
        case = cases_by_id.get(cid)
        if case is None:
            raise ManifestValidationError(
                f"manifest case_id={cid!r} not in case bank — fail closed"
            )
        expected = str(row.get("hash") or "").strip()
        live = compute_case_hash(case)
        if expected and expected != live:
            raise ManifestValidationError(
                f"manifest hash mismatch for {cid}: "
                f"manifest={expected} live={live}"
            )


def _case_prompt(case: Mapping[str, Any]) -> str:
    for key in ("prompt", "query", "user_input"):
        s = str(case.get(key) or "").strip()
        if s:
            return s
    turns = case.get("turns")
    if isinstance(turns, list):
        for turn in turns:
            if not isinstance(turn, Mapping):
                continue
            for key in ("user", "content", "prompt", "input", "query"):
                s = str(turn.get(key) or "").strip()
                if s:
                    return s
    return ""


def _case_success_criteria(case: Mapping[str, Any]) -> Dict[str, Any]:
    crit = case.get("success_criteria")
    if isinstance(crit, Mapping) and crit:
        return {
            "must_contain": list(crit.get("must_contain") or []),
            "must_not_contain": list(crit.get("must_not_contain") or []),
        }
    rubric = case.get("rubric") if isinstance(case.get("rubric"), Mapping) else {}
    if rubric:
        return rubric_to_success_criteria(rubric)
    # KB / code_review / multi_agent fixtures: derive light lexical anchors.
    must: List[str] = []
    for key in ("expected_final", "expected_ids", "gold"):
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            must.append(val.strip())
        elif isinstance(val, (list, tuple)):
            must.extend(str(x).strip() for x in val if str(x).strip())
    return {"must_contain": must[:6], "must_not_contain": []}


def _case_as_task(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Project capability case into typed-plan task shape for stub/score helpers."""
    rubric = case.get("rubric") if isinstance(case.get("rubric"), Mapping) else {}
    criteria = _case_success_criteria(case)
    prompt = _case_prompt(case)
    return {
        "task_id": str(case.get("case_id") or ""),
        "case_id": str(case.get("case_id") or ""),
        "category": str(case.get("category") or ""),
        "user_input": prompt,
        "prompt": prompt,
        "success_criteria": criteria,
        "rubric": dict(rubric),
        "capabilities": list(case.get("capabilities") or []),
        "scripted_answer": str(case.get("scripted_answer") or "").strip(),
    }


def _resolve_exam_bank(
    *,
    profile: Optional[Mapping[str, Any]],
    profile_id: str,
    cases: Optional[Sequence[Mapping[str, Any]]],
) -> Tuple[List[Dict[str, Any]], str]:
    """Load Subject-matched seed bank (never silently substitute agent for others)."""
    from core.apps.eval.service.capability_case_bank import get_suite_profile
    from core.apps.eval.service.subject_suite_profiles import (
        SubjectSuiteProfileError,
        load_cases_for_suite_profile,
        normalize_suite_profile,
        resolve_subject_kind_from_profile,
    )

    if cases is not None:
        bank = [dict(c) for c in cases if isinstance(c, Mapping)]
        kind = "agent"
        try:
            if profile is not None:
                kind = resolve_subject_kind_from_profile(
                    normalize_suite_profile(profile)
                )
            elif profile_id:
                kind = resolve_subject_kind_from_profile(
                    normalize_suite_profile(
                        get_suite_profile(str(profile_id).strip())
                    )
                )
        except (ValueError, SubjectSuiteProfileError) as exc:
            _log.debug("subject_kind label fallback agent: %s", exc)
            kind = "agent"
        return bank, kind or "agent"

    pid = str(profile_id or "").strip()
    try:
        if profile is not None:
            prof = normalize_suite_profile(dict(profile))
        else:
            prof = normalize_suite_profile(
                get_suite_profile(pid or "agent.regression.v1")
            )
        kind = resolve_subject_kind_from_profile(prof) or "agent"
        bank = load_cases_for_suite_profile(prof)
        return bank, kind
    except (SubjectSuiteProfileError, ValueError) as exc:
        if not pid or pid.startswith("agent."):
            _log.debug("agent bank fallback after resolve failure: %s", exc)
            return list(build_agent_capability_cases()), "agent"
        raise SuiteProfileExamError(str(exc)) from exc


def _resolve_exam_workspace_id(explicit: str = "") -> str:
    wid = str(explicit or "").strip()
    if wid:
        return wid
    try:
        from core.harness.named_workspace.resolve import get_active_named_workspace

        ctx = get_active_named_workspace()
        return str(getattr(ctx, "workspace_id", "") or "").strip() if ctx else ""
    except Exception:
        return ""


def _persist_exam_summary(out: Dict[str, Any], *, workspace_id: str = "") -> None:
    try:
        from core.apps.eval.service.suite_exam_summary_store import (
            record_suite_exam_summary,
        )

        record_suite_exam_summary(out, workspace_id=workspace_id)
    except Exception as exc:  # noqa: BLE001 — ledger must not break exam
        _log.debug("suite exam summary persist skipped: %s", exc)


async def run_suite_profile_exam(
    *,
    profile_id: str = "agent.regression.v1",
    profile: Optional[Mapping[str, Any]] = None,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    live: bool = False,
    model: str = "",
    run_key: str = "",
    object_id: str = "",
    object_version: str = "0.1.0",
    max_cases: int = 0,
    workspace_id: str = "",
) -> Dict[str, Any]:
    """Compile Profile Plan → require sample_manifest → execute only those cases."""
    wid = _resolve_exam_workspace_id(workspace_id)
    bank, subject_kind = _resolve_exam_bank(
        profile=profile, profile_id=profile_id, cases=cases
    )
    by_id = index_cases_by_id(bank)

    plan = compile_plan_from_suite_profile(
        profile=profile,
        profile_id=str(profile_id or "").strip(),
        cases=bank,
        object_id=object_id,
        object_version=object_version,
    )
    subject_kind = str(plan.get("subject_kind") or subject_kind or "agent")

    try:
        sample_manifest = require_sample_manifest(plan)
        verify_capability_manifest_hashes(sample_manifest, by_id)
    except ManifestValidationError as e:
        fail: Dict[str, Any] = {
            "ok": False,
            "error": str(e),
            "profile_id": plan.get("profile_id") or profile_id,
            "subject_kind": subject_kind,
            "live": bool(live),
            "accuracy_claim": False,
            "sufficiency_claim": False,
            "claim_eligible": False,
            "msg": (
                "Suite Profile exam fail closed: sample_manifest required "
                "(no full-pack / selected_cases fallback)"
            ),
        }
        fail = attach_evaluation_plan(fail, plan)
        _persist_exam_summary(fail, workspace_id=wid)
        return fail

    run_id = f"suite-profile-{uuid.uuid4().hex[:12]}"
    rk = str(run_key or "").strip() or run_id
    plan = dict(plan)
    plan["execution_fingerprint"] = compute_execution_fingerprint(
        plan_id=str(plan.get("plan_id") or ""),
        manifest_hash=str(plan.get("manifest_hash") or ""),
        runner_id="suite_profile_exam",
        run_key=rk,
    )

    limit = int(max_cases or 0)
    rows = list(sample_manifest)
    if limit > 0:
        rows = rows[:limit]

    started = time.time()
    task_rows: List[Dict[str, Any]] = []
    totals = {"pass": 0, "fail": 0, "inconclusive": 0, "error": 0, "tasks": 0}

    for row in rows:
        cid = str(row.get("case_id") or "").strip()
        case = by_id.get(cid)
        if case is None:
            totals["error"] += 1
            task_rows.append(
                {
                    "case_id": cid,
                    "status": "error",
                    "summary": "case missing from bank after manifest verify",
                }
            )
            continue
        if bool(row.get("holdout")) or bool(case.get("holdout")):
            # Holdout must not execute on the eval path (tuning exclusion).
            task_rows.append(
                {
                    "case_id": cid,
                    "status": "skipped",
                    "summary": "holdout excluded from suite profile exam",
                    "holdout": True,
                }
            )
            continue

        task = _case_as_task(case)
        criteria = task["success_criteria"]
        totals["tasks"] += 1
        try:
            if live:
                output = await live_llm_output(
                    str(task.get("user_input") or ""), model_name=model
                )
            elif task.get("scripted_answer"):
                output = str(task.get("scripted_answer") or "")
            else:
                output = dry_stub_output(task)
            scored = score_lexical_output(output, criteria)
            st = str(scored.get("status") or "inconclusive")
            if st in totals:
                totals[st] += 1
            else:
                totals["inconclusive"] += 1
            task_rows.append(
                {
                    "case_id": cid,
                    "capability_id": row.get("capability_id")
                    or (case.get("capabilities") or [None])[0],
                    "status": st,
                    "summary": scored.get("summary"),
                    "output_excerpt": str(output)[:500],
                    "live": bool(live),
                    "oracle": "lexical",
                    "holdout": False,
                }
            )
        except Exception as e:  # noqa: BLE001 — per-case isolation
            _log.warning("suite profile case failed %s: %s", cid, e, exc_info=True)
            totals["error"] += 1
            task_rows.append(
                {
                    "case_id": cid,
                    "status": "error",
                    "summary": str(e)[:200],
                    "live": bool(live),
                }
            )

    out: Dict[str, Any] = {
        "ok": True,
        "run_id": run_id,
        "run_key": rk,
        "profile_id": plan.get("profile_id"),
        "subject_kind": subject_kind,
        "object_type_member": bool(plan.get("object_type_member")),
        "live": bool(live),
        "manifest_hash": plan.get("manifest_hash"),
        "execution_fingerprint": plan.get("execution_fingerprint"),
        "manifest_case_count": len(sample_manifest),
        "executed_case_count": totals["tasks"],
        "cases": task_rows,
        "counts": totals,
        "duration_s": round(time.time() - started, 3),
        "claim_eligible": False,
        "accuracy_claim": False,
        "sufficiency_claim": False,
        "msg": (
            f"Suite Profile exam ({subject_kind}) · sample_manifest sole execution "
            "list · lexical/scripted oracle · accuracy_claim=false · dry≠live claim"
            if not live
            else (
                f"Suite Profile exam ({subject_kind}) · sample_manifest sole "
                "execution list · lexical oracle on live LLM · accuracy_claim=false"
            )
        ),
        "honesty": (
            f"Runner executed only sample_manifest rows for subject={subject_kind}; "
            "bank matched profile Subject; selected_cases ignored; holdout skipped; "
            "claim_eligible=false"
        ),
    }
    out = attach_evaluation_plan(out, plan)
    from core.apps.eval.service.suite_profile_report import build_suite_profile_report

    out["report"] = build_suite_profile_report(out, cases=bank)
    _persist_exam_summary(out, workspace_id=wid)
    out["exam_summary_workspace_id"] = wid
    return out
