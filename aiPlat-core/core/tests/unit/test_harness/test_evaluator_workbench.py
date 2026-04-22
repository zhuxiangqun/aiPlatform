import anyio


def test_evaluator_workbench_threshold_gate():
    from core.harness.evaluation.workbench import EvaluatorThresholds, apply_threshold_gate, validate_report

    report = {"pass": True, "score": {"functionality": 6}}
    ok, _ = validate_report(report)
    assert ok is True
    gated = apply_threshold_gate(report, EvaluatorThresholds(functionality_min=7))
    assert gated["pass"] is False
    assert isinstance(gated.get("issues"), list)

