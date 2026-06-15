"""
Guard regression self-tests — deliberately construct violation scenarios to verify guards catch them.

Each test:
  1. Constructs a minimal violation scenario (mock skill/agent data, temp dirs, etc.)
  2. Runs the guard/lint check
  3. Asserts that the violation IS detected

Purpose: prevent guards from degrading (e.g., a rule accidentally removed from YAML, a pattern
that no longer matches after refactoring).
"""

import os
import tempfile
import pytest
from pathlib import Path


class TestGuardRegression:
    """Verify that guard rules still detect known violation patterns."""

    def test_lint_detects_missing_handler_for_scripts(self):
        """ExecTypeDirectoryMismatch should catch scripts/ without handler.py."""
        from core.management.lint_rules.metadata import ExecTypeDirectoryMismatch

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scripts").mkdir()
            (root / "scripts" / "main.py").write_text("print('hello')")
            # NO handler.py — this should be detected

            class FakeSkill:
                name = "test_skill"
                execution_type = "prompt"
                metadata = {"skill_dir": str(root)}

            rule = ExecTypeDirectoryMismatch()
            issues = rule.check(FakeSkill())
            has_scripts_but_prompt = any(
                "should be handler" in i.message for i in issues
            )
            assert has_scripts_but_prompt, (
                "ExecTypeDirectoryMismatch should WARN when scripts/*.py exists "
                "but execution_type=prompt"
            )

    def test_lint_detects_nested_skill_dir(self):
        """NestedSkillDirectory should catch skills/<name>/ nesting."""
        from core.management.lint_rules.metadata import NestedSkillDirectory

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested = root / "skills" / "test_skill"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text("---\nname: test\n---\n# Test")

            class FakeSkill:
                name = "test_skill"
                metadata = {"skill_dir": str(root)}

            rule = NestedSkillDirectory()
            issues = rule.check(FakeSkill())
            has_nested = any("nested skills" in i.message for i in issues)
            assert has_nested, (
                "NestedSkillDirectory should detect nested skills/test_skill/ structure"
            )

    def test_lint_agent_bare_detects_no_tools(self):
        """AgentToolBinding should catch agents with no skills or tools."""
        from core.management.lint_rules.agent_metadata import AgentToolBinding

        class FakeSkill:
            name = "bare_agent"
            metadata = {"skills": [], "tools": []}

        rule = AgentToolBinding()
        issues = rule.check(FakeSkill())
        assert len(issues) == 1
        assert "cannot perform actions" in issues[0].message

    def test_lint_agent_missing_required_fields(self):
        """AgentFrontmatterCompleteness should catch missing name/agent_type."""
        from core.management.lint_rules.agent_metadata import AgentFrontmatterCompleteness

        class FakeSkill:
            name = "incomplete"
            metadata = {}  # missing name and agent_type

        rule = AgentFrontmatterCompleteness()
        issues = rule.check(FakeSkill())
        errors = [i for i in issues if i.level == "error"]
        assert len(errors) >= 2, f"Expected at least 2 errors for missing required fields, got {len(errors)}"

    def test_lint_mcp_transport_requires_command(self):
        """McpTransportValidation should catch stdio without command."""
        from core.management.lint_rules.mcp_config import McpTransportValidation

        class FakeSkill:
            name = "broken_mcp"
            metadata = {"transport": "stdio", "command": ""}

        rule = McpTransportValidation()
        issues = rule.check(FakeSkill())
        assert len(issues) == 1
        assert "command" in issues[0].message

    def test_lint_workflow_missing_trigger(self):
        """WorkflowTriggerValidation should catch missing trigger."""
        from core.management.lint_rules.workflow_structure import WorkflowTriggerValidation

        class FakeSkill:
            name = "triggerless"
            metadata = {}

        rule = WorkflowTriggerValidation()
        issues = rule.check(FakeSkill())
        assert len(issues) == 1
        assert "No trigger" in issues[0].message

    def test_compliance_matrix_loads(self):
        """Compliance matrix YAML should be valid and have all required fields."""
        import yaml
        # Go up from tests/unit/ → tests/ → core/ → core/management/
        matrix_path = Path(__file__).parent.parent.parent / "management" / "compliance_matrix.yaml"
        if not matrix_path.exists():
            pytest.skip("compliance_matrix.yaml not found")
        with open(matrix_path) as f:
            data = yaml.safe_load(f)
        requirements = data.get("requirements", []) if isinstance(data, dict) else data
        assert isinstance(requirements, list), f"Expected requirements list, got {type(requirements)}"
        assert len(requirements) > 0, "Compliance matrix has zero requirements"
        for req in requirements:
            assert "id" in req, f"Requirement missing id: {req}"
            assert "requirement" in req, f"Requirement {req.get('id')} missing description"
            assert "severity" in req, f"Requirement {req.get('id')} missing severity"
            checks = req.get("checks", [])
            assert len(checks) > 0, (
                f"Requirement {req['id']} has ZERO checks — compliance gap! "
                f"Add at least one check or remove the requirement."
            )

    def test_all_lint_rules_discoverable(self):
        """All lint rules in lint_rules/ should be auto-discovered."""
        from core.management.skill_linter_base import LintRule, RuleRegistry

        registry = RuleRegistry()
        core_root = Path(__file__).parent.parent.parent  # tests/unit/ → tests/ → core/
        rules_dir = core_root / "management" / "lint_rules"
        py_files = [f for f in rules_dir.iterdir() if f.suffix == ".py" and not f.name.startswith("_")]
        assert len(py_files) >= 3, f"Expected at least 3 lint rule modules, found {len(py_files)}"

        # Verify auto-discovery works
        registry._load_python_rules()
        rule_count = len(registry._rules)
        assert rule_count >= 5, f"Expected at least 5 lint rules after discovery, found {rule_count}"
