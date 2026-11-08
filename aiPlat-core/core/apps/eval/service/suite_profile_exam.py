"""Suite Profile exam — execute only ``sample_manifest`` (ADR nail 2).

Runs capability-bank cases referenced by a Profile-compiled Plan v2.
Dry = deterministic lexical fixture; live = LLM + lexical oracle.
Never opens claim_eligible / accuracy_claim.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

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


def _case_as_task(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Project capability case into typed-plan task shape for stub/score helpers."""
    rubric = case.get("rubric") if isinstance(case.get("rubric"), Mapping) else {}
    criteria = rubric_to_success_criteria(rubric)
    return {
        "task_id": str(case.get("case_id") or ""),
        "case_id": str(case.get("case_id") or ""),
        "category": str(case.get("category") or ""),
        "user_input": str(case.get("prompt") or case.get("user_input") or ""),
        "prompt": str(case.get("prompt") or ""),
        "success_criteria": criteria,
        "rubric": dict(rubric),
        "capabilities": list(case.get("capabilities") or []),
    }


async def run_suite_profile_exam(
    *,
    profile_id: str = "agent.regression.v1",
    profile: Optional[Mapping[str, Any]] = None,
    cases: Optional[Sequence[Mapping[str, Any]]] = None,
    live: bool = False,
    model: str = "",
    run_key: str = "",
    object_id: str = "agent.capability.target",
    object_version: str = "0.1.0",
    max_cases: int = 0,
) -> Dict[str, Any]:
    """Compile Profile Plan → require sample_manifest → execute only those cases."""
    bank = list(cases) if cases is not None else build_agent_capability_cases()
    by_id = index_cases_by_id(bank)

    plan = compile_plan_from_suite_profile(
        profile=profile,
        profile_id=str(profile_id or "").strip(),
        cases=bank,
        object_id=object_id,
        object_version=object_version,
    )

    try:
        sample_manifest = require_sample_manifest(plan)
        verify_capability_manifest_hashes(sample_manifest, by_id)
    except ManifestValidationError as e:
        fail: Dict[str, Any] = {
            "ok": False,
            "error": str(e),
            "accuracy_claim": False,
            "sufficiency_claim": False,
            "claim_eligible": False,
            "msg": (
                "Suite Profile exam fail closed: sample_manifest required "
                "(no full-pack / selected_cases fallback)"
            ),
        }
        return attach_evaluation_plan(fail, plan)

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
            "Suite Profile exam · sample_manifest sole execution list · "
            "lexical oracle · accuracy_claim=false · dry≠live subject claim"
            if not live
            else (
                "Suite Profile exam · sample_manifest sole execution list · "
                "lexical oracle on live LLM · accuracy_claim=false"
            )
        ),
        "honesty": (
            "Runner executed only sample_manifest rows; selected_cases ignored; "
            "holdout skipped; claim_eligible=false"
        ),
    }
    out = attach_evaluation_plan(out, plan)
    from core.apps.eval.service.suite_profile_report import build_suite_profile_report

    out["report"] = build_suite_profile_report(out, cases=bank)
    return out
