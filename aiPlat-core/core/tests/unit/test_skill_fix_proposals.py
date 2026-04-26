from core.management.skill_linter import lint_skill, propose_skill_fixes


def test_propose_fix_missing_markdown():
    skill = {
        "id": "s1",
        "name": "s1",
        "description": "desc desc",
        "metadata": {"executable": True, "permissions": ["llm:generate"], "trigger_conditions": ["x"]},
        "input_schema": {"a": {"type": "string"}},
        "output_schema": {"text": {"type": "string", "required": True}},
    }
    lint = lint_skill(skill)
    fixes = propose_skill_fixes(skill=skill, lint=lint)
    # Should propose adding markdown when lint has missing_markdown
    assert any(f.get("issue_code") == "missing_markdown" for f in (fixes.get("fixes") or []))


def test_propose_fix_missing_permissions():
    # executable but no permissions -> missing_permissions lint error -> propose fix
    skill = {
        "id": "s2",
        "name": "s2",
        "description": "desc desc",
        "metadata": {"executable": True, "permissions": [], "trigger_conditions": ["x"]},
        "input_schema": {"a": {"type": "string"}},
        "output_schema": {"text": {"type": "string", "required": True}, "markdown": {"type": "string", "required": True}},
    }
    lint = lint_skill(skill)
    fixes = propose_skill_fixes(skill=skill, lint=lint)
    assert any(f.get("issue_code") == "missing_permissions" for f in (fixes.get("fixes") or []))

