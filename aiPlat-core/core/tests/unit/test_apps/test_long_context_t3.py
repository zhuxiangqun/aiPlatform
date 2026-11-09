"""T3 long-context generator / A9 judge / v1.1 scope lift smoke."""
from __future__ import annotations

from core.apps.eval.service.capability_case_bank import (
    build_agent_capability_cases,
    validate_agent_capability_bank,
)
from core.apps.eval.service.capability_id_map import (
    V1_IN_SCOPE,
    V1_OUT_OF_SCOPE,
    is_v1_in_scope,
)
from core.apps.eval.service.long_context_generator import (
    generate_long_context_case,
    judge_long_context,
)
from core.apps.eval.service.subject_adapter import get_subject_adapter
from core.apps.eval.service.tool_capability_fixtures import (
    load_tool_capability_fixture_cases,
    run_tool_fixture_suite,
)


def test_generate_and_judge_long_context():
    case = generate_long_context_case(
        case_id="tmp.lc",
        must_retain_claims=["FACT-A", "FACT-B"],
        tier="ci_short",
    )
    j = judge_long_context(case, {"answer": case["scripted_answer"]})
    assert j["passed"] is True
    bad = judge_long_context(case, {"answer": "nope"})
    assert bad["passed"] is False


def test_a9_fixture_suite():
    rows = load_tool_capability_fixture_cases(capability_id="long_context")
    assert len(rows) >= 5
    report = run_tool_fixture_suite(capability_id="long_context")
    assert report["ok"] is True, report


def test_v1_1_scope_includes_tool_session_long():
    assert is_v1_in_scope("tool_selection") is True
    assert is_v1_in_scope("multi_turn_memory") is True
    assert is_v1_in_scope("long_context") is True
    assert V1_OUT_OF_SCOPE == frozenset()
    assert "long_context" in V1_IN_SCOPE


def test_bank_merges_fixture_positives():
    cases = build_agent_capability_cases()
    assert len(cases) >= 64 + 25  # 5 caps × ≥5 positives
    caps = set()
    for c in cases:
        for x in c.get("capabilities") or []:
            caps.add(str(x))
    for need in (
        "tool_selection",
        "tool_args",
        "tool_result_use",
        "multi_turn_memory",
        "long_context",
    ):
        assert need in caps
    report = validate_agent_capability_bank(cases)
    assert report["ok"] is True, report.get("t0_inscope_contracts") or report


def test_adapter_long_context_path():
    adapter = get_subject_adapter("agent")
    case = generate_long_context_case(
        case_id="adapter.lc",
        must_retain_claims=["Z-99"],
        tier="ci_short",
    )
    exe = adapter.execute(case)
    assert exe["status"] == "ok"
    j = adapter.judge(case, exe)
    assert j["passed"] is True
    n = adapter.normalize(case, exe, j)
    assert n["v1_in_scope"] is True
    assert n["claim_eligible"] is False
