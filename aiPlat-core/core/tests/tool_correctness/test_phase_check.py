"""
Tool self-tests: verify phase_check.sh correctness.

Tests run the actual bash script and verify:
  - The 5 steps are all invoked
  - Steps that should PASS actually PASS
  - The summary section correctly reports FAILURES
  - Exit code reflects actual failures
"""
import subprocess
from pathlib import Path
import pytest

# Heavy integration self-test: invokes real full-repo phase_check.sh (slow, 95s+).
# Skipped in the fast architecture guard; run explicitly via `pytest -m slow`.
pytestmark = pytest.mark.slow

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
PHASE_CHECK = str(WORKSPACE_ROOT / "scripts" / "phase_check.sh")


def _run_script(timeout=300):
    """Run phase_check.sh and return (exit_code, stdout)."""
    result = subprocess.run(
        ["bash", PHASE_CHECK],
        capture_output=True, text=True, timeout=timeout,
        cwd=str(WORKSPACE_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


class TestPhaseCheckStructure:

    def test_all_5_steps_invoked(self):
        """The output should show Step 1 through Step 5 headers."""
        code, stdout, stderr = _run_script(timeout=300)
        combined = stdout + stderr
        for step in ["Step 1/5", "Step 2/5", "Step 2.5/5", "Step 3/5", "Step 4/5", "Step 5/5"]:
            assert step in combined, f"Missing step header: {step}"

    def test_summary_section_present(self):
        """The output should have a summary section."""
        code, stdout, stderr = _run_script(timeout=300)
        combined = stdout + stderr
        assert "PHASE CHECK" in combined, "Missing PHASE CHECK header"
        assert "step" in combined.lower(), "No step count in summary"

    def test_exit_code_matches_failure_count(self):
        """Exit code should be non-zero if any step failed."""
        code, stdout, stderr = _run_script(timeout=300)
        combined = stdout + stderr
        # If text says "FAILED", exit code should be non-zero
        has_fail = "FAILED" in combined and "PHASE CHECK FAILED" in combined
        if has_fail:
            assert code != 0, f"Reported FAILED but exit code is {code}"
        else:
            # If PASSED, exit code should be 0
            assert code == 0, f"Reported PASSED but exit code is {code}"


class TestPhaseCheckWiringTests:

    def test_wiring_tests_exist_and_pass(self):
        """Step 2 should find and run tests/wiring/ successfully."""
        code, stdout, stderr = _run_script(timeout=300)
        combined = stdout + stderr
        assert "test_wiring.py" in combined or "test_methods_wired" in combined, \
            "Wiring test files not found in output"
        # Step 2 should report PASS (wiring tests are clean)
        step2_section = combined.split("Step 2/5")[1].split("Step")[0] if "Step 2/5" in combined else ""
        assert "PASS" in step2_section or "passed" in step2_section.lower(), \
            f"Step 2 should PASS: {step2_section[:300]}"


class TestPhaseCheckIntegrationTests:

    def test_integration_tests_exist(self):
        """Step 3 should find integration test files."""
        code, stdout, stderr = _run_script(timeout=300)
        combined = stdout + stderr
        assert "integration" in combined.lower(), \
            "Integration tests not mentioned in output"

    def test_integration_tests_pass(self):
        """Step 3 should report PASS for integration tests."""
        code, stdout, stderr = _run_script(timeout=300)
        combined = stdout + stderr
        if "Step 3/5" in combined:
            step3_section = combined.split("Step 3/5")[1]
            if "Step 4" in step3_section:
                step3_section = step3_section.split("Step 4")[0]
            assert "PASS" in step3_section or "passed" in step3_section.lower(), \
                f"Step 3 should PASS: {step3_section[:300]}"
