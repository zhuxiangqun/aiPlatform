def test_evaluation_policy_from_dict_defaults():
    from core.harness.evaluation.policy import EvaluationPolicy, DEFAULT_POLICY

    pol = EvaluationPolicy.from_dict(None).to_dict()
    assert pol["schema_version"] == DEFAULT_POLICY["schema_version"]
    assert "thresholds" in pol
    assert "weights" in pol
    assert "regression_gate" in pol
    assert "tag_templates" in pol
    assert "default_tag_template" in pol
