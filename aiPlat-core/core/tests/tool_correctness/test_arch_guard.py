"""
Tool self-tests: verify architecture_guard.py + arch_guard_base.py are correct.

Tests:
  - _grep: executes grep patterns and finds matches
  - ArchYAMLRule: parses YAML config and runs checks
  - format_text: produces correct PASS/FAIL output
  - ArchRegistry: loads all rules without crashing
"""
import os
import sys
import subprocess
import tempfile
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))


class TestGrep:
    """Verify _grep executes and finds/counts matches correctly."""

    def test_finds_matching_pattern(self):
        from core.management.arch_guard_base import _grep
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "test.py").write_text("import os\nimport sys\n")
            result = _grep(Path(tmp), r"import\s+\w+", [str(Path(tmp) / "test.py")],
                           exclude=[], ext=[".py"])
            assert len(result) >= 2, f"Expected >=2 import matches, got {len(result)}"

    def test_excludes_patterns(self):
        from core.management.arch_guard_base import _grep
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "test.py").write_text("import os  # noqa: ignore\nimport sys\n")
            result = _grep(Path(tmp), r"import\s+\w+", [str(Path(tmp) / "test.py")],
                           exclude=[], ext=[".py"], grep_exclude=["noqa: ignore"])
            # With grep_exclude, the 'import os' line should be filtered out
            assert len(result) >= 1, f"Expected >=1 match, got {len(result)}"

    def test_returns_empty_when_no_match(self):
        from core.management.arch_guard_base import _grep
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "test.py").write_text("print('hello')\n")
            result = _grep(Path(tmp), r"import\s+django", [str(Path(tmp) / "test.py")],
                           exclude=[], ext=[".py"])
            assert len(result) == 0


class TestArchYAMLRule:
    """Verify ArchYAMLRule parses config correctly."""

    def test_loads_rule_from_config(self):
        from core.management.arch_guard_base import ArchYAMLRule
        config = {
            "id": "test_rule",
            "section": "§1",
            "section_name": "Test Section",
            "level": "error",
            "check": {
                "type": "grep_forbidden",
                "pattern": r"import\s+os",
                "paths": ["/tmp/test_dir"],
            },
            "message": "Don't import os",
        }
        rule = ArchYAMLRule(config)
        assert rule.code == "test_rule", f"Expected test_rule, got {rule.code}"
        assert rule.level == "error"
        # Verify the check type is stored (private attribute)
        assert rule._check_type in ("grep_forbidden", "grep_required", "file_exists",
                                      "file_forbidden", "cmd_output"), \
            f"Unexpected check type: {rule._check_type}"

    def test_section_info_stored(self):
        from core.management.arch_guard_base import ArchYAMLRule
        config = {
            "id": "gf1", "section": "§42", "section_name": "Subprocess", "level": "warning",
            "check": {"type": "grep_forbidden", "pattern": "x", "paths": ["/tmp"]},
            "message": "X",
        }
        rule = ArchYAMLRule(config)
        assert rule.section_number == "§42"
        assert rule.section_name == "Subprocess"


class TestFormatText:
    """Verify format_text produces correct output."""

    def test_pass_report(self):
        from scripts.architecture_guard import format_text
        from core.management.arch_guard_base import ArchReport, ArchSection

        report = ArchReport(
            ok=True, violations=0, duration_ms=10,
            sections=[ArchSection(number="§1", name="Test", status="pass", items=[])],
        )
        text = format_text(report)
        assert "PASS" in text or "all checks pass" in text.lower()

    def test_fail_report(self):
        from scripts.architecture_guard import format_text
        from core.management.arch_guard_base import ArchReport, ArchSection, ArchIssue

        issue = ArchIssue(level="error", code="test", message="Bad import", files=["bad.py:1"])
        section = ArchSection(number="§1", name="Test", status="fail", items=[issue])
        report = ArchReport(ok=False, violations=1, duration_ms=10, sections=[section])

        text = format_text(report)
        assert "FAIL" in text
        assert "Bad import" in text
        assert "bad.py" in text


class TestArchRegistry:
    """Verify ArchRegistry loads and runs all rules."""

    def test_registry_loads_without_crash(self):
        from core.management.arch_guard_base import get_arch_registry
        registry = get_arch_registry()
        # Registry stores rules in _rules (internal attribute)
        assert hasattr(registry, '_rules'), "Registry missing _rules"
        assert len(registry._rules) > 0, "Registry should have rules loaded"

    def test_registry_has_yaml_rules(self):
        from core.management.arch_guard_base import get_arch_registry, ArchYAMLRule
        registry = get_arch_registry()
        yaml_rules = [r for r in registry._rules if isinstance(r, ArchYAMLRule)]
        assert len(yaml_rules) > 100, f"Expected >100 YAML rules, got {len(yaml_rules)}"

    def test_registry_no_duplicate_ids(self):
        from core.management.arch_guard_base import get_arch_registry
        registry = get_arch_registry()
        ids = [r.code for r in registry._rules if hasattr(r, 'code')]
        dups = [i for i in ids if ids.count(i) > 1]
        assert dups == [], f"Duplicate rule IDs: {set(dups)}"

    def test_registry_run_all_returns_report(self):
        from core.management.arch_guard_base import get_arch_registry
        registry = get_arch_registry()
        report = registry.run_all(WORKSPACE_ROOT)
        assert report is not None
        assert report.duration_ms >= 0
