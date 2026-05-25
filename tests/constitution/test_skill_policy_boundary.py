"""
test_skill_policy_boundary.py — Skill vs Internal Policy boundary enforcement.

Encodes CLAUDE.md §5.10 rules as automated checks:
  1. No Skill-to-Skill nesting (skills/ must not call sys_skill_call)
  2. Skill 化准入标准 documentation (5 criteria enforced via code review)

Context: Skills are reusable execution units. Internal Policy (routing,
classification, decision logic) belongs in core/apps/*, not skills/.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = ROOT / "aiPlat-core" / "core" / "apps" / "skills"


# ═══════════════════════════════════════════════════════════════════════
# §SP1: No Skill-to-Skill nesting
# Per CLAUDE.md §5.10: Skills MUST NOT call sys_skill_call directly.
# Skill composition should be done by the Agent or Internal Policy.
# Exception: SkillExecutor (executor.py) is infrastructure, not a business Skill.
# ═══════════════════════════════════════════════════════════════════════


class TestNoSkillToSkillNesting:
    """Skills must not call other Skills directly."""

    def test_no_sys_skill_call_in_skills(self):
        """Business Skills must not import or call sys_skill_call."""
        violations = []
        exempt = re.compile(r"executor\.py|__init__\.py|__pycache__|test_")

        for f in sorted(SKILLS_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for pat in [r"import sys_skill_call", r"from.*sys_skill_call",
                         r"sys_skill_call\("]:
                for m in re.finditer(pat, text):
                    line_no = text[: m.start()].count("\n") + 1
                    violations.append(
                        f"  {f.relative_to(ROOT)}:{line_no}: {m.group()}"
                    )

        assert not violations, (
            f"Skills MUST NOT call sys_skill_call directly (no Skill-to-Skill nesting). "
            f"Use Agent-level orchestration or Internal Policy instead. "
            f"SkillExecutor (executor.py) is the only allowed exception. "
            f"Found {len(violations)} violations:\n" + "\n".join(violations[:10])
        )

    def test_skill_executor_is_the_only_sys_skill_caller(self):
        """SkillExecutor is the ONLY allowed sys_skill_call user in skills/."""
        executor = SKILLS_DIR / "executor.py"
        if not executor.exists():
            return
        text = executor.read_text(errors="ignore")
        assert "sys_skill_call" in text, (
            "SkillExecutor must use sys_skill_call to execute skills "
            "through the standard safety boundary"
        )


# ═══════════════════════════════════════════════════════════════════════
# §SP2: Skill 化准入标准 (documentation check)
# These 5 criteria from CLAUDE.md §5.10 are enforced via code review.
# This test documents the standard so it's visible in CI output.
# ═══════════════════════════════════════════════════════════════════════


class TestSkillQualificationCriteria:
    """Document the 5 criteria for Skill qualification (per CLAUDE.md §5.10).

    These are NOT auto-enforced — they require human judgment. This test
    exists to make the criteria visible in every CI run as a reminder.
    """

    SKILL_CRITERIA = [
        "1. 该能力是否可独立执行？",
        "2. 是否有清晰稳定的输入输出边界？",
        "3. 是否会被多个 Agent / API 独立复用？",
        "4. 是否需要独立的权限、灰度、观测、治理？",
        "5. 是否属于执行单元而非高层决策逻辑？",
    ]

    def test_skill_criteria_documented(self):
        """Verify the 5 Skill 化准入标准 are documented in CLAUDE.md."""
        claude_md = ROOT / "aiPlat-core" / "CLAUDE.md"
        if not claude_md.exists():
            return
        text = claude_md.read_text(errors="ignore")
        for criterion in self.SKILL_CRITERIA:
            assert criterion in text, (
                f"Skill 化准入标准 missing from CLAUDE.md: {criterion}"
            )

    def test_known_internal_policies(self):
        """Verify known Internal Policy modules are in core/apps/, not skills/."""
        internal_policy_modules = [
            "document_intelligence/question_analysis.py",
            "document_intelligence/retrieval_policy.py",
            "document_intelligence/answer_strategy.py",
            "document_intelligence/strategy_resolver.py",
            "document_intelligence/classifier.py",
        ]
        missing = []
        for mod in internal_policy_modules:
            path = ROOT / "aiPlat-core" / "core" / "apps" / mod
            if not path.exists():
                missing.append(mod)

        assert not missing, (
            f"Internal Policy modules must exist in core/apps/, not skills/. "
            f"Missing: {missing}"
        )

    def test_no_decision_logic_in_skills(self):
        """Skills should NOT contain if/else routing or classification logic.

        Decision logic belongs in Internal Policy (core/apps/*).
        This is a weak heuristic: checks for common routing/classification patterns.
        """
        violations = []
        exempt = re.compile(r"executor\.py|registry\.py|__init__\.py|test_|evolution/")

        # Patterns that suggest decision logic (not Skill execution)
        decision_patterns = [
            r"if\s+query_type\s*==\s*",
            r"if\s+domain\s*==\s*",
            r"if\s+category\s*==\s*",
            r"classify_document\b",
        ]

        for f in sorted(SKILLS_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            for pat in decision_patterns:
                for m in re.finditer(pat, text):
                    line_no = text[: m.start()].count("\n") + 1
                    violations.append(
                        f"  {f.relative_to(ROOT)}:{line_no}: {m.group()}"
                    )

        assert not violations, (
            f"Skills should not contain decision/routing logic "
            f"(belongs in Internal Policy: core/apps/*). "
            f"Found {len(violations)} potential violations:\n" + "\n".join(violations[:10])
        )


# ═══════════════════════════════════════════════════════════════════════
# §SP3: Skill→Tool dependency visibility
# Informational only — records which Skills depend on which Tools.
# ═══════════════════════════════════════════════════════════════════════


class TestSkillToolDependencies:
    """Document Skill→Tool dependencies for visibility."""

    def test_skill_tool_usage_visible(self):
        """Record which Skills call sys_tool_call (informational, not blocking)."""
        dependencies = {}
        exempt = re.compile(r"executor\.py|registry\.py|__init__\.py|test_|evolution/")

        for f in sorted(SKILLS_DIR.rglob("*.py")):
            if exempt.search(str(f)):
                continue
            try:
                text = f.read_text(errors="ignore")
            except Exception:
                continue
            tool_calls = re.findall(r"sys_tool_call\((\w+)", text)
            if tool_calls:
                dependencies[f.stem] = list(set(tool_calls))

        if dependencies:
            print(f"\n  Skill→Tool dependencies: {dependencies}")
        else:
            print("\n  Skill→Tool dependencies: (none)")
        assert True
