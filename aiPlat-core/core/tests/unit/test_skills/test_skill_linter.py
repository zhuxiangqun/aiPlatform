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
    # missing_markdown is a warning-level rule (lint_rules.yaml) — assert the
    # issue is surfaced in the report, not necessarily as an error.
    s = lint_summary(rep)
    assert (s["error_count"] + s["warning_count"]) >= 1
    codes = {w.get("code") for w in (rep.get("warnings") or [])}
    assert "missing_markdown" in codes


def test_linter_high_risk_blocks_on_errors():
    rep = lint_skill(
        {
            "id": "s2",
            # missing name → missing_name (error-level rule) — high-risk permission
            # + any error must block
            "description": "desc desc",
            "category": "analysis",
            "metadata": {"executable": True, "permissions": ["tool:run_command"], "trigger_conditions": ["x"]},
            "input_schema": {"a": {"type": "string"}},
            "output_schema": {"report": {"type": "object"}},
        }
    )
    s = lint_summary(rep)
    assert s["risk_level"] == "high"
    assert s["error_count"] >= 1
    assert s["blocked"] is True

