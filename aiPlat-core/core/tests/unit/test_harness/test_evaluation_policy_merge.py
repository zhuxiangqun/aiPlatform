def test_merge_policy_deep_merge():
    from core.harness.evaluation.policy import merge_policy

    base = {"thresholds": {"functionality_min": 7}, "regression_gate": {"required_tags": ["a"], "max_new_console_errors": 0}}
    override = {"regression_gate": {"required_tags": ["b"]}}
    merged = merge_policy(base, override)
    assert merged["thresholds"]["functionality_min"] == 7
    assert merged["regression_gate"]["required_tags"] == ["b"]
    assert merged["regression_gate"]["max_new_console_errors"] == 0

