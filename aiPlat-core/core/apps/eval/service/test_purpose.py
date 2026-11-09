"""EvalCase test_purpose schema v1 validate (Case Pack P0).

Authority: docs/architecture/plans/CASE_TEST_PURPOSE_SCHEMA_V1.md (Frozen).
Mechanical checks only — purpose_mismatch / prompt_leak human gates stay separate.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

PURPOSE_SCHEMA = "eval.case_test_purpose.v1"

_REQUIRED_STR = ("summary", "why_this_case", "oracle_rationale")
_REQUIRED_LISTS = ("expected_behavior", "failure_signals", "not_testing")

_GENERIC_SUMMARY = frozenset(
    {
        "测试 agent",
        "测试agent",
        "看是否正常",
        "是否正常",
        "综合评估",
        "测试一下",
        "正常测试",
        "test agent",
        "test the agent",
        "general evaluation",
        "smoke test",
    }
)

_GENERIC_EXPECTED = frozenset(
    {
        "回答正确",
        "表现良好",
        "输出正确",
        "正确回答",
        "works correctly",
        "correct answer",
        "good response",
    }
)

_ORACLE_HINT = re.compile(
    r"must_contain|must_not|tool_trace|rubric|exact|schema|gold|判分|规则|词面|oracle",
    re.IGNORECASE,
)


def _nonempty_str(v: Any) -> str:
    return str(v or "").strip()


def _str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, (list, tuple)):
        out: List[str] = []
        for x in v:
            s = _nonempty_str(x)
            if s:
                out.append(s)
        return out
    return []


def validate_test_purpose(
    purpose: Mapping[str, Any] | None,
    *,
    prompt: str = "",
    capabilities: Optional[Sequence[str]] = None,
) -> List[str]:
    """Return list of machine-check error codes; empty = pass.

    Codes: missing_field:*, empty_list:*, purpose_too_generic,
    oracle_rationale_no_signal, prompt_contains_purpose_leak,
    linked_capabilities_outside_case.
    """
    errors: List[str] = []
    if not isinstance(purpose, Mapping):
        return ["missing_field:test_purpose"]

    for key in _REQUIRED_STR:
        if not _nonempty_str(purpose.get(key)):
            errors.append(f"missing_field:{key}")

    for key in _REQUIRED_LISTS:
        items = _str_list(purpose.get(key))
        if not items:
            errors.append(f"empty_list:{key}")

    summary = _nonempty_str(purpose.get("summary"))
    if summary and (
        summary.lower() in _GENERIC_SUMMARY
        or len(summary) < 8
    ):
        errors.append("purpose_too_generic")

    expected = _str_list(purpose.get("expected_behavior"))
    if expected and all(e.lower() in _GENERIC_EXPECTED for e in expected):
        errors.append("purpose_too_generic")

    rationale = _nonempty_str(purpose.get("oracle_rationale"))
    if rationale and not _ORACLE_HINT.search(rationale):
        errors.append("oracle_rationale_no_signal")

    # Mechanical leak: prompt must not contain failure_signals / full purpose dump.
    prompt_s = str(prompt or "")
    if prompt_s:
        for sig in _str_list(purpose.get("failure_signals")):
            if len(sig) >= 8 and sig in prompt_s:
                errors.append("prompt_contains_purpose_leak")
                break
        summary_s = _nonempty_str(purpose.get("summary"))
        if summary_s and len(summary_s) >= 12 and summary_s in prompt_s:
            errors.append("prompt_contains_purpose_leak")

    linked = _str_list(purpose.get("linked_capabilities"))
    if linked and capabilities is not None:
        allowed = {str(c).strip().lower() for c in capabilities if str(c).strip()}
        for lid in linked:
            if lid.lower() not in allowed:
                errors.append("linked_capabilities_outside_case")
                break

    # Deduplicate while preserving order
    seen = set()
    uniq: List[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq


def assert_test_purpose_valid(
    purpose: Mapping[str, Any] | None,
    *,
    prompt: str = "",
    capabilities: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Raise ValueError with joined codes if invalid; else return normalized dict."""
    errs = validate_test_purpose(
        purpose, prompt=prompt, capabilities=capabilities
    )
    if errs:
        raise ValueError("test_purpose_invalid:" + ",".join(errs))
    assert isinstance(purpose, Mapping)
    return {
        "summary": _nonempty_str(purpose.get("summary")),
        "why_this_case": _nonempty_str(purpose.get("why_this_case")),
        "expected_behavior": _str_list(purpose.get("expected_behavior")),
        "failure_signals": _str_list(purpose.get("failure_signals")),
        "not_testing": _str_list(purpose.get("not_testing")),
        "oracle_rationale": _nonempty_str(purpose.get("oracle_rationale")),
        **(
            {"notes": _nonempty_str(purpose.get("notes"))}
            if _nonempty_str(purpose.get("notes"))
            else {}
        ),
        **(
            {"linked_capabilities": _str_list(purpose.get("linked_capabilities"))}
            if _str_list(purpose.get("linked_capabilities"))
            else {}
        ),
    }
