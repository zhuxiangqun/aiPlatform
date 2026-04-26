def test_unique_preserve_order():
    from core.harness.evaluation.coverage_gate import unique_preserve_order

    assert unique_preserve_order(["a", "a", " ", "b", "b", "c"]) == ["a", "b", "c"]


def test_evaluate_coverage_missing():
    from core.harness.evaluation.coverage_gate import evaluate_coverage

    ok, missing = evaluate_coverage(["login", "create", "save"], ["login", "save"])
    assert ok is False
    assert missing == ["create"]

