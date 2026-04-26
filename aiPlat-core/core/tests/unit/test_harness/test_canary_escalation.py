from core.harness.canary.escalation import (
    change_id_for_canary,
    change_id_for_release_candidate,
    consecutive_failures_from_reports,
    is_p0_report,
    should_escalate,
)


def test_change_id_deterministic():
    a = change_id_for_canary("canary:demo")
    b = change_id_for_canary("canary:demo")
    assert a == b
    assert a.startswith("chg-canary-")
    c = change_id_for_release_candidate("art-rc-1")
    d = change_id_for_release_candidate("art-rc-1")
    assert c == d
    assert c.startswith("chg-rc-")


def test_consecutive_failures():
    # newest-first: fail, fail, pass
    reports = [{"pass": False}, {"status": "failed"}, {"pass": True}]
    assert consecutive_failures_from_reports(reports) == 2


def test_is_p0_report():
    assert is_p0_report({"issues": [{"severity": "P0"}]}) is True
    assert is_p0_report({"issues": [{"severity": "P1"}]}) is False


def test_should_escalate():
    rep = {"issues": [{"severity": "P0"}]}
    assert (
        should_escalate(
            enabled=True,
            p0_only=True,
            consecutive_failures_threshold=2,
            new_report=rep,
            new_consecutive_failures=2,
        )
        is True
    )
    assert (
        should_escalate(
            enabled=True,
            p0_only=True,
            consecutive_failures_threshold=2,
            new_report={"issues": [{"severity": "P1"}]},
            new_consecutive_failures=2,
        )
        is False
    )
