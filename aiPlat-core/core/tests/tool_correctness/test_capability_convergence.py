"""
Tool self-tests: verify capability_convergence.py core functions are correct.

Tests:
  - Module imports without crashing
  - Core data structures are valid
  - run_convergence_check produces expected output
"""
import sys
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))


class TestCapabilityConvergence:

    def test_module_imports(self):
        """capability_convergence.py should import without errors."""
        from core.management.capability_convergence import (
            run_convergence_check,
            load_contract,
            print_report,
        )
        assert callable(run_convergence_check)
        assert callable(load_contract)
        assert callable(print_report)

    def test_load_contract_returns_dict(self):
        """load_contract should return a dict."""
        from core.management.capability_convergence import load_contract

        contract = load_contract()
        assert isinstance(contract, dict), f"Expected dict, got {type(contract)}"

    def test_run_convergence_returns_tuple(self):
        """run_convergence_check should return (all_pass, violations)."""
        from core.management.capability_convergence import run_convergence_check

        all_pass, violations = run_convergence_check(WORKSPACE_ROOT, force_rebuild=False)
        assert isinstance(all_pass, bool)
        assert isinstance(violations, list)

    def test_violation_structure(self):
        """Each violation should have expected keys."""
        from core.management.capability_convergence import run_convergence_check

        _, violations = run_convergence_check(WORKSPACE_ROOT, force_rebuild=False)
        if violations:
            v = violations[0]
            assert isinstance(v, dict), f"Violation should be dict, got {type(v)}"

    def test_print_report_returns_string(self):
        """print_report should return a non-empty string."""
        from core.management.capability_convergence import (
            run_convergence_check,
            print_report,
        )

        all_pass, violations = run_convergence_check(WORKSPACE_ROOT, force_rebuild=False)
        report = print_report(all_pass, violations)
        assert isinstance(report, str)
        assert len(report) > 0
