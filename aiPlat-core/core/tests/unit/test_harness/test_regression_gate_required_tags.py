def test_regression_gate_required_tags():
    from core.harness.evaluation.evidence_diff import evaluate_regression

    diff = {"metrics": {"new_console_errors": 0, "new_network_5xx": 0, "new_network_4xx": 0}}
    gate = {"max_new_console_errors": 0, "max_new_network_5xx": 0, "max_new_network_4xx": 0, "required_tags": ["login", "save"]}
    is_reg, reasons = evaluate_regression(diff, gate, executed_tags=["login"])
    assert is_reg is True
    assert any("缺失关键路径标签" in r for r in reasons)

