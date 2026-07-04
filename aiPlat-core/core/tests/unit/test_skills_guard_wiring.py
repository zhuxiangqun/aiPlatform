"""Integration tests: SkillsGuard integration with SkillRegistry wiring."""
import os
import tempfile
import pytest
from core.harness.infrastructure.gates.skills_guard import reset_skills_guard
from core.apps.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def reset():
    reset_skills_guard()
    yield
    reset_skills_guard()


@pytest.fixture
def safe_skill_dir():
    """Create a safe skill directory."""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("---\nname: safe-skill\nversion: 1.0.0\n---\n# Safe Skill\nA safe utility skill.\n")
        with open(os.path.join(d, "handler.py"), "w") as f:
            f.write("def execute(p):\n    return {'ok': True}\n")
        yield d


@pytest.fixture
def dangerous_skill_dir():
    """Create a skill directory with dangerous code."""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("---\nname: bad-skill\nversion: 1.0.0\n---\n# Bad Skill\n")
        with open(os.path.join(d, "handler.py"), "w") as f:
            f.write("import os\n")
            f.write("def execute(p):\n")
            f.write("    os.system(p['cmd'])\n")  # BLOCKER: os.system
            f.write("    eval(p['expr'])\n")      # BLOCKER: eval
        yield d


class TestSkillsGuardWiring:
    def test_guard_module_importable(self):
        """SkillsGuard should be importable without circular deps."""
        from core.harness.infrastructure.gates.skills_guard import (
            SkillsGuard, get_skills_guard, ScanResult, ThreatLevel, ThreatFinding,
        )
        guard = get_skills_guard()
        assert guard is not None
        assert len(guard.list_rules()) > 70

    def test_safe_skill_scan_passes(self, safe_skill_dir):
        """A skill with no dangerous patterns should pass the guard."""
        from core.harness.infrastructure.gates.skills_guard import get_skills_guard
        guard = get_skills_guard()
        result = guard.scan_skill("safe-skill", safe_skill_dir)
        assert result.passed
        assert result.blocker_count == 0
        assert result.critical_count == 0

    def test_dangerous_skill_scan_fails(self, dangerous_skill_dir):
        """A skill with os.system + eval should be blocked."""
        from core.harness.infrastructure.gates.skills_guard import get_skills_guard
        guard = get_skills_guard()
        result = guard.scan_skill("bad-skill", dangerous_skill_dir)
        assert not result.passed
        assert result.blocker_count > 0

    def test_scan_content_rejects_eval(self):
        """Inline content with eval should be detected."""
        from core.harness.infrastructure.gates.skills_guard import get_skills_guard
        guard = get_skills_guard()
        result = guard.scan_content("eval('1+1')", "test.py")
        assert not result.passed

    def test_scan_content_rejects_os_system(self):
        """Inline content with os.system should be detected."""
        from core.harness.infrastructure.gates.skills_guard import get_skills_guard
        guard = get_skills_guard()
        result = guard.scan_content("import os\nos.system('ls')", "handler.py")
        assert not result.passed

    def test_scan_content_rejects_secrets(self):
        """Hardcoded API keys should be detected."""
        from core.harness.infrastructure.gates.skills_guard import get_skills_guard
        guard = get_skills_guard()
        result = guard.scan_content(
            'api_key: "sk-1234567890abcdefghijklmnopqrstuvwxyz1234"', "config.py"
        )
        assert not result.passed
        assert result.critical_count > 0

    def test_scan_content_accepts_safe_code(self):
        """Safe code should pass the guard."""
        from core.harness.infrastructure.gates.skills_guard import get_skills_guard
        guard = get_skills_guard()
        result = guard.scan_content(
            "def process(data):\n    return sum(data)", "util.py"
        )
        assert result.passed

    def test_guard_stats_match_expected(self):
        """Guard stats should match the 70+ pattern catalogue."""
        from core.harness.infrastructure.gates.skills_guard import get_skills_guard
        guard = get_skills_guard()
        stats = guard.get_stats()
        assert stats["total_rules"] > 70
        assert "categories" in stats
        # Each category should have rules
        cats = stats["categories"]
        assert len(cats) >= 10  # 11+ categories
