from core.management.skill_linter import lint_skill, lint_summary


def test_linter_requires_output_schema_markdown():
    rep = lint_skill(
        {
            "id": "s1",
            "name": "s1",
            "description": "desc desc",
            "category": "analysis",
            "metadata": {"executable": True, "permissions": ["llm:generate"], "trigger_conditions": ["x"]},
            "input_schema": {"a": {"type": "string"}},
            "output_schema": {"report": {"type": "object"}},
        }
    )
    assert lint_summary(rep)["error_count"] >= 1


def test_linter_high_risk_blocks_on_errors():
    rep = lint_skill(
        {
            "id": "s2",
            "name": "s2",
            "description": "desc desc",
            "category": "analysis",
            "metadata": {"executable": True, "permissions": ["tool:run_command"], "trigger_conditions": ["x"]},
            "input_schema": {"a": {"type": "string"}},
            "output_schema": {"report": {"type": "object"}},  # missing markdown -> error
        }
    )
    s = lint_summary(rep)
    assert s["risk_level"] == "high"
    assert s["blocked"] is True

