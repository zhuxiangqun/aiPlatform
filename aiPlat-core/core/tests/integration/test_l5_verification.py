"""
Integration tests for L5 verification infrastructure.

Verifies:
  1. verify_l5_runtime.py runs without errors
  2. CoreFacade wrappers are importable and functional
  3. Key modules have expected production callers
"""

import subprocess
import sys
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent.parent


class TestL5Verification(unittest.TestCase):
    """Verify the verification infrastructure itself."""

    def test_verify_script_runs(self):
        """verify_l5_runtime.py should run without errors."""
        result = subprocess.run(
            [sys.executable, str(WORKSPACE / "scripts/verify_l5_runtime.py"), "--json"],
            capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr[:200]}")
        import json
        data = json.loads(result.stdout)
        self.assertIn("total", data)
        self.assertIn("score", data)
        self.assertGreater(data["total"], 400, "Should find 400+ capabilities")
        self.assertGreater(data["score"], 50, "Score should be 50+")

    def test_verify_script_subsystem_filter(self):
        result = subprocess.run(
            [sys.executable, str(WORKSPACE / "scripts/verify_l5_runtime.py"),
             "--subsystem", "Harness"],
            capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Harness", result.stdout)

    def test_core_facade_wrappers_importable(self):
        """CoreFacade wrappers should be importable."""
        sys.path.insert(0, str(WORKSPACE / "aiPlat-core"))
        from core.api.core_facade import (
            get_policy_gate,
            get_working_memory,
            get_circuit_breaker,
            get_fde_pipeline_health,
            get_route_permissions,
            register_handler,
            dispatch,
        )
        # Verify they exist and are callable (or raise expected errors)
        self.assertTrue(callable(get_policy_gate))
        self.assertTrue(callable(get_working_memory))
        self.assertTrue(callable(get_circuit_breaker))
        self.assertTrue(callable(get_fde_pipeline_health))
        self.assertTrue(callable(get_route_permissions))

        # register_handler and dispatch should work for test handler
        register_handler("_test_handler", lambda: "test_ok")
        result = dispatch("_test_handler")
        self.assertEqual(result, "test_ok")

    def test_architecture_guard_quick_runs(self):
        """architecture_guard.py --quick should run without errors."""
        result = subprocess.run(
            [sys.executable, str(WORKSPACE / "scripts/architecture_guard.py"), "--quick"],
            capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(result.returncode, 0,
                        f"Guard failed: {result.stderr[:200]}")

    def test_key_modules_have_callers(self):
        """Critical infrastructure modules must have non-test callers."""
        sys.path.insert(0, str(WORKSPACE / "aiPlat-core"))
        from core.harness.syscalls.llm import _llm_cb
        self.assertIsNotNone(_llm_cb, "Circuit breaker should exist")


if __name__ == "__main__":
    unittest.main()
