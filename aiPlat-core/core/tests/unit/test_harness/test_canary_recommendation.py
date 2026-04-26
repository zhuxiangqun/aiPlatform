from core.harness.canary.recommendation import recommend_action


def test_recommend_block_on_regression():
    action, reason = recommend_action({"pass": False, "regression": {"is_regression": True, "reasons": ["x"]}})
    assert action == "block"
    assert "regression_gate" in reason


def test_recommend_block_on_p0():
    action, reason = recommend_action({"pass": False, "issues": [{"severity": "P0", "title": "bad"}]})
    assert action == "block"
    assert "P0:" in reason


def test_recommend_investigate_on_fail_no_p0():
    action, _ = recommend_action({"pass": False, "issues": [{"severity": "P1"}]})
    assert action == "investigate"


def test_recommend_continue_on_pass():
    action, _ = recommend_action({"pass": True})
    assert action == "continue"

