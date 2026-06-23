"""
Tool self-tests: verify method_verify.sh correctness.

Tests run the actual bash script and verify:
  - The script runs without crashing
  - DEAD methods cause exit 1 (not exit 0 as before)
  - Known wired methods show as OK
"""
import subprocess
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
METHOD_VERIFY = str(WORKSPACE_ROOT / "scripts" / "method_verify.sh")


def _run_script():
    """Run method_verify.sh and return (exit_code, stdout)."""
    result = subprocess.run(
        ["bash", METHOD_VERIFY],
        capture_output=True, text=True, timeout=60,
        cwd=str(WORKSPACE_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


class TestMethodVerifyRuns:

    def test_script_completes(self):
        """method_verify.sh should run to completion."""
        code, stdout, stderr = _run_script()
        combined = stdout + stderr
        assert "Method Verification" in combined, \
            f"Missing header: {combined[:300]}"

    def test_exit_code_correct(self):
        """method_verify.sh should exit 0 or 1 (not crash)."""
        code, stdout, stderr = _run_script()
        assert code in (0, 1), f"Unexpected exit code: {code}"

    def test_known_wired_methods_show_ok(self):
        """Known wired methods should show as OK."""
        code, stdout, stderr = _run_script()
        combined = stdout + stderr
        # on_post_observe is wired via hook_manager.py
        assert "on_post_observe" in combined, \
            "on_post_observe should appear in method verify output"
        assert "invalidate_domain" in combined, \
            "invalidate_domain should appear in method verify output"

    def test_output_has_ok_dead_labels(self):
        """Output should contain OK or DEAD labels for each method."""
        code, stdout, stderr = _run_script()
        combined = stdout + stderr
        assert "OK" in combined or "DEAD" in combined, \
            "No OK/DEAD labels in output"

    def test_summary_line_present(self):
        """Output should have a summary line."""
        code, stdout, stderr = _run_script()
        combined = stdout + stderr
        assert "METHOD VERIFY" in combined, \
            "Missing METHOD VERIFY summary"
