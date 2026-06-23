"""
Tool self-tests: verify eval_retrieval.py and eval_calibration.py core functions.

Tests:
  - Module imports without errors
  - RAG evaluation functions exist and are callable
  - Calibration evaluation functions exist and are callable
"""
import sys
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))


class TestEvalRetrieval:

    def test_module_imports(self):
        """eval_retrieval.py should import without errors."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "eval_retrieval",
            str(WORKSPACE_ROOT / "scripts" / "eval_retrieval.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod is not None

    def test_has_evaluation_functions(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "eval_retrieval",
            str(WORKSPACE_ROOT / "scripts" / "eval_retrieval.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # eval_retrieval.py should have evaluate functions
        functions = [n for n in dir(mod) if callable(getattr(mod, n, None)) and not n.startswith('_')]
        assert len(functions) > 0, f"No public callables found in eval_retrieval: {functions}"


class TestEvalCalibration:

    def test_module_imports(self):
        """eval_calibration.py should import without errors."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "eval_calibration",
            str(WORKSPACE_ROOT / "scripts" / "eval_calibration.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod is not None

    def test_has_calibration_functions(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "eval_calibration",
            str(WORKSPACE_ROOT / "scripts" / "eval_calibration.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        functions = [n for n in dir(mod) if callable(getattr(mod, n, None)) and not n.startswith('_')]
        assert len(functions) > 0, f"No public callables in eval_calibration: {functions}"
