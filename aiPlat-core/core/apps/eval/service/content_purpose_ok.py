"""ADR P1 content-level purpose_ok audit (claim stays false).

Mechanical ``test_purpose`` schema checks are necessary but not sufficient.
This module audits seed/workspace cases against the §5.4 checklist subset that
is machine-checkable, so promote cannot stamp purpose_ok on empty oracles /
stub prompts. Does **not** open accuracy_claim or certification.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.test_purpose import validate_test_purpose

CONTENT_PURPOSE_SCHEMA = "eval.content_purpose_ok.v1"

_MIN_PROMPT_LEN = 4  # allow short ambiguous prompts (clarification)
_SHORT_PROMPT_LEN = 8
_SAMPLE_FAIL_LIMIT = 8
_CLARIFY_CAPS = frozenset(
    {
        "clarification",
        "multi_turn_memory",
        "tool_selection",
        "tool_args",
        "tool_result_use",
    }
)


class ContentPurposeOkError(ValueError):
    """Content purpose_ok gate failed (fail closed)."""


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


def _nonempty_list(v: Any) -> List[Any]:
    if isinstance(v, (list, tuple)):
        return [x for x in v if x is not None and str(x).strip()]
    return []


def _has_oracle_anchor(case: Mapping[str, Any]) -> bool:
    """True when a judge can distinguish pass/fail without live side effects."""
    rubric = case.get("rubric") if isinstance(case.get("rubric"), Mapping) else {}
    if _nonempty_list(rubric.get("must_contain")) or _nonempty_list(
        rubric.get("must_not_contain")
    ):
        return True

    crit = (
        case.get("success_criteria")
        if isinstance(case.get("success_criteria"), Mapping)
        else {}
    )
    if _nonempty_list(crit.get("must_contain")) or _nonempty_list(
        crit.get("must_not_contain")
    ):
        return True

    for key in (
        "gold",
        "expected_final",
        "expected_ids",
        "expected_tools",
        "expected_handoff_path",
        "findings",
        "must_contain_from_tools",
    ):
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            return True
        if _nonempty_list(val):
            return True
        if isinstance(val, Mapping) and val:
            return True

    turns = case.get("turns")
    if isinstance(turns, list):
        for turn in turns:
            if not isinstance(turn, Mapping):
                continue
            for key in (
                "must_contain",
                "must_not_contain",
                "expected",
                "expected_behavior",
                "gold",
            ):
                val = turn.get(key)
                if isinstance(val, str) and val.strip():
                    return True
                if _nonempty_list(val):
                    return True
                if isinstance(val, Mapping) and val:
                    return True
    return False


def audit_case_content_purpose(case: Mapping[str, Any]) -> List[str]:
    """Return machine-check error codes; empty = content_purpose ready.

    Args:
        case: case 参数。
    """
    errors: List[str] = []
    if not isinstance(case, Mapping):
        return ["case_not_mapping"]

    case_id = str(case.get("case_id") or "").strip() or "<missing_case_id>"
    prompt = _case_prompt(case)
    caps = [str(c).strip() for c in (case.get("capabilities") or []) if str(c).strip()]

    if not case_id or case_id == "<missing_case_id>":
        errors.append("missing_field:case_id")
    if not caps:
        errors.append("empty_list:capabilities")

    purpose = case.get("test_purpose")
    purpose_errs = validate_test_purpose(
        purpose if isinstance(purpose, Mapping) else None,
        prompt=prompt,
        capabilities=caps,
    )
    errors.extend(purpose_errs)

    if len(prompt) < _MIN_PROMPT_LEN:
        errors.append("prompt_too_short")
    elif len(prompt) < _SHORT_PROMPT_LEN:
        # Short prompts OK when testing underspec / tool micro-probes with purpose.
        caps_l = {c.lower() for c in caps}
        why = ""
        if isinstance(purpose, Mapping):
            why = str(purpose.get("why_this_case") or "").strip()
        if not (caps_l & _CLARIFY_CAPS) and len(why) < _SHORT_PROMPT_LEN:
            errors.append("prompt_too_short")

    if not _has_oracle_anchor(case):
        errors.append("oracle_anchor_missing")

    # Dedup preserve order
    seen = set()
    out: List[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def audit_cases_content_purpose(
    cases: Sequence[Mapping[str, Any]],
    *,
    subject_kind: str = "",
) -> Dict[str, Any]:
    """Audit a case list; ok=true only when every case passes.

    Args:
        cases: 用例列表。
        subject_kind: subject_kind 参数。
    """
    rows: List[Dict[str, Any]] = []
    ok_n = 0
    for raw in cases:
        case = raw if isinstance(raw, Mapping) else {}
        errs = audit_case_content_purpose(case)
        cid = str(case.get("case_id") or "").strip() or "<missing>"
        if errs:
            rows.append({"case_id": cid, "ok": False, "errors": errs})
        else:
            ok_n += 1
    fail_n = len(cases) - ok_n
    sample = rows[:_SAMPLE_FAIL_LIMIT]
    return {
        "schema": CONTENT_PURPOSE_SCHEMA,
        "ok": fail_n == 0 and len(cases) > 0,
        "subject_kind": str(subject_kind or "").strip(),
        "case_count": len(cases),
        "content_purpose_ok_count": ok_n,
        "content_purpose_fail_count": fail_n,
        "content_purpose_ready": fail_n == 0 and len(cases) > 0,
        "failures": sample,
        "accuracy_claim": False,
        "claim_eligible": False,
        "certification_eligible": False,
        "honesty": (
            "content_purpose_ok is machine checklist only (§5.4 subset); "
            "≠ human sign-off completeness; ≠ accuracy_claim / certification."
        ),
    }


def assert_cases_content_purpose_ok(
    cases: Sequence[Mapping[str, Any]],
    *,
    subject_kind: str = "",
) -> Dict[str, Any]:
    """Fail closed before purpose_ok stamp / promote freeze.

    Args:
        cases: 用例列表。
        subject_kind: subject_kind 参数。
    """
    report = audit_cases_content_purpose(cases, subject_kind=subject_kind)
    if not report.get("ok"):
        sample = report.get("failures") or []
        raise ContentPurposeOkError(
            "content_purpose_ok_failed:"
            f"subject={subject_kind or '?'} "
            f"fail={report.get('content_purpose_fail_count')} "
            f"sample={sample}"
        )
    return report


def _load_subject_cases(subject_kind: str) -> List[Dict[str, Any]]:
    kind = str(subject_kind or "").strip().lower()
    if not kind:
        raise ContentPurposeOkError("subject_kind required")
    if kind == "agent":
        from core.apps.eval.service.capability_case_bank import (
            build_agent_capability_cases,
        )

        return list(build_agent_capability_cases())

    from core.apps.eval.service.subject_capability_promote import _bank_specs

    spec = _bank_specs().get(kind)
    if spec is None:
        raise ContentPurposeOkError(f"no_content_purpose_subject:{kind}")
    return list(spec["build"]())


def content_purpose_ok_for_subject(subject_kind: str) -> Dict[str, Any]:
    """Audit one Subject seed bank for content purpose readiness.

    Args:
        subject_kind: subject_kind 参数。
    """
    from core.apps.eval.service.method_track import assert_not_subject_method

    kind = str(subject_kind or "").strip().lower()
    assert_not_subject_method(kind)
    cases = _load_subject_cases(kind)
    report = audit_cases_content_purpose(cases, subject_kind=kind)
    report["pack_source"] = "workspace_seeds"
    return report


def content_purpose_ok_inventory() -> Dict[str, Any]:
    """Honesty matrix: content_purpose_ok across promotable Subject banks."""
    from core.apps.eval.service.subject_capability_promote import (
        list_promotable_subject_kinds,
    )

    subjects: List[Dict[str, Any]] = []
    for kind in list_promotable_subject_kinds():
        try:
            report = content_purpose_ok_for_subject(kind)
            subjects.append(
                {
                    "subject_kind": kind,
                    "ok": bool(report.get("ok")),
                    "case_count": int(report.get("case_count") or 0),
                    "content_purpose_ok_count": int(
                        report.get("content_purpose_ok_count") or 0
                    ),
                    "content_purpose_fail_count": int(
                        report.get("content_purpose_fail_count") or 0
                    ),
                    "content_purpose_ready": bool(report.get("content_purpose_ready")),
                    "failures": list(report.get("failures") or [])[:3],
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001 — inventory fail-soft per row
            subjects.append(
                {
                    "subject_kind": kind,
                    "ok": False,
                    "case_count": 0,
                    "content_purpose_ok_count": 0,
                    "content_purpose_fail_count": 0,
                    "content_purpose_ready": False,
                    "failures": [],
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )

    ready_n = sum(1 for s in subjects if s["content_purpose_ready"])
    fail_cases = sum(int(s["content_purpose_fail_count"] or 0) for s in subjects)
    return {
        "schema": CONTENT_PURPOSE_SCHEMA,
        "ok": all(bool(s.get("ok")) for s in subjects) and len(subjects) > 0,
        "subject_count": len(subjects),
        "content_purpose_ready_count": ready_n,
        "content_purpose_fail_case_total": fail_cases,
        "subjects": subjects,
        "accuracy_claim": False,
        "claim_eligible": False,
        "certification_eligible": False,
        "honesty": (
            "ADR P1 content purpose_ok inventory; machine checklist ≠ claim; "
            "promote stamps purpose_ok only when content_purpose_ready."
        ),
        "next_action": (
            "Fix failing cases (oracle/prompt/test_purpose) then promote; "
            "do not open claim from content_purpose_ok alone."
        ),
        "review_links": {
            "subject_inventory_tab": "/eval?tab=subject-regression-inventory",
            "case_packs_tab": "/eval?tab=case-packs",
            "p1_regression_tab": "/eval?tab=p1-regression",
        },
    }
