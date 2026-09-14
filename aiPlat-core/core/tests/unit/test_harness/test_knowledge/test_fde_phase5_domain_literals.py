"""Phase 5: fde_domain_literals is error and behavior-fork clean."""

from __future__ import annotations

from pathlib import Path

from core.management.arch_guard_rules.fde_workbench import FdeDomainLiteralsAstCheck


def test_fde_domain_literals_is_error_and_clean():
    rule = FdeDomainLiteralsAstCheck()
    assert rule.level == "error"
    # .../aiPlat-core/core/tests/unit/test_harness/test_knowledge/this.py → parents[6]=workspace
    root = Path(__file__).resolve().parents[6]
    if not (root / "aiPlat-core").is_dir():
        root = Path.cwd()
    issues = rule.check(root)
    assert issues == [], f"unexpected domain literal forks: {issues[:5]}"
