"""Leading-token eval verdict helpers — reject mid-string false approvals."""

from core.harness.execution.eval_verdict import (
    is_approved_evaluation,
    is_leading_token,
    is_pass_keyword_verdict,
    is_yes_review,
    parse_status_line_pass,
)
from core.harness.execution.langgraph.graphs.reflection import ReflectionGraph


def test_is_leading_token():
    assert is_leading_token("APPROVED", "APPROVED")
    assert is_leading_token("APPROVED: ok", "APPROVED")
    assert is_leading_token("approved looks good", "APPROVED")
    assert is_leading_token("PASS：中文", "PASS")
    assert not is_leading_token("NOT APPROVED", "APPROVED")
    assert not is_leading_token("DISAPPROVED", "APPROVED")
    assert not is_leading_token("result is APPROVED", "APPROVED")
    assert not is_leading_token("BYPASS", "PASS")
    assert not is_leading_token("", "PASS")


def test_is_approved_evaluation():
    assert is_approved_evaluation("APPROVED")
    assert is_approved_evaluation("APPROVED: all criteria met")
    assert not is_approved_evaluation("REJECTED: missing tests")
    assert not is_approved_evaluation("NOT APPROVED")
    assert not is_approved_evaluation("The output is APPROVED by style")
    assert not is_approved_evaluation("")


def test_parse_status_line_pass():
    assert parse_status_line_pass("STATUS: PASS\nSCORES: x=1") is True
    assert parse_status_line_pass("STATUS: REJECTED\nFEEDBACK: no") is False
    assert parse_status_line_pass("STATUS: BYPASS") is False
    assert parse_status_line_pass("no status here") is None


def test_is_pass_keyword_verdict_status_wins():
    # Mid-string PASS / BYPASS must not approve without STATUS or leading token.
    assert not is_pass_keyword_verdict("quality BYPASS review\nFEEDBACK: none")
    assert not is_pass_keyword_verdict("NOT A PASS overall")
    assert is_pass_keyword_verdict("PASS\nSCORES: factuality=0.9")
    assert is_pass_keyword_verdict("STATUS: PASS\nFEEDBACK: ok")
    assert not is_pass_keyword_verdict("PASS leading but\nSTATUS: FAIL")
    assert not is_pass_keyword_verdict("STATUS: BYPASS\nother PASS noise")


def test_reflection_parse_rejects_bypass_substring():
    graph = ReflectionGraph()
    # Old bug: "PASS" in "BYPASS".upper() → false approve.
    result = graph._parse_critic_result(
        "STATUS: BYPASS\nSCORES: factuality=0.9\nFEEDBACK: ignore"
    )
    assert result.passed is False

    result2 = graph._parse_critic_result(
        "notes mention bypass criteria\nFEEDBACK:\n- still incomplete"
    )
    assert result2.passed is False

    result3 = graph._parse_critic_result(
        "STATUS: PASS\nSCORES: factuality=0.9 completeness=0.8 clarity=0.9 format=0.85\nFEEDBACK: None"
    )
    assert result3.passed is True


def test_is_yes_review_leading_only():
    # Old bug: "YES" in "NO — do not answer YES" → false approve.
    assert is_yes_review("YES")
    assert is_yes_review("YES: looks good")
    assert is_yes_review("yes with feedback")
    assert not is_yes_review("NO")
    assert not is_yes_review("NO: missing tests")
    assert not is_yes_review("NO — do not answer YES")
    assert not is_yes_review("The answer is YES later")
    assert not is_yes_review("")
