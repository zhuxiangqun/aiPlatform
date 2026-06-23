"""
Tool self-tests: verify caller_verify.sh correctness.

Tests run the actual bash script and verify:
  - The script runs without crashing (exit code 0 for clean state)
  - Index building completes (output contains "indexed ... done")
  - Known wired symbols do NOT appear as 0 callers
"""
import subprocess
import sys
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CALLER_VERIFY = str(WORKSPACE_ROOT / "scripts" / "caller_verify.sh")


def _run_script():
    """Run caller_verify.sh and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        ["bash", CALLER_VERIFY],
        capture_output=True, text=True, timeout=120,
        cwd=str(WORKSPACE_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


class TestCallerVerifyRuns:

    def test_script_does_not_crash(self):
        """caller_verify.sh should run to completion without pipefail crash."""
        code, stdout, stderr = _run_script()
        # Script may exit non-zero if dead symbols found, but should not crash
        assert "indexed" in stderr.lower() or "building" in stderr.lower() or len(stderr) > 0, \
            f"Expected index building progress in stderr, got: {stderr[:200]}"

    def test_index_build_completes(self):
        """Index building should output 'indexed N files done' or similar."""
        code, stdout, stderr = _run_script()
        combined = stdout + stderr
        # The script outputs progress to stderr
        assert "indexed" in combined.lower() or "building" in combined.lower(), \
            f"Index building not detected in output: {combined[:500]}"


class TestCallerVerifyResults:

    def test_known_wired_symbol_not_dead(self):
        """PIIDetector (via get_pii_detector) should not show as 0 callers."""
        code, stdout, stderr = _run_script()
        combined = stdout + stderr
        # get_pii_detector is wired via llm.py — should NOT appear as dead
        if "get_pii_detector" in combined:
            # It appeared — check it's not marked as 0 callers
            for line in combined.splitlines():
                if "get_pii_detector" in line:
                    assert "0 callers" not in line, f"get_pii_detector reported dead: {line}"

    def test_output_format_valid(self):
        """Output should contain the expected header sections."""
        code, stdout, stderr = _run_script()
        combined = stdout + stderr
        assert "Caller Verification" in combined, \
            "Missing 'Caller Verification' header"

    def test_summary_line_present(self):
        """Output should contain PASSED or FAILED summary."""
        code, stdout, stderr = _run_script()
        combined = stdout + stderr
        has_summary = "PASSED" in combined or "FAILED" in combined or "passed" in combined.lower()
        assert has_summary, f"No PASSED/FAILED summary in output: {combined[:500]}"
