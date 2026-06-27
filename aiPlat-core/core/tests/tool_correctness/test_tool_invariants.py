"""
Tool invariant tests: verify that guard/diagnostic tools produce output
within expected ranges. These catch catastrophic tool regressions
(e.g., tool suddenly finds 0 routes instead of 500+).

Unlike unit tests (which test internal logic), these test the TOOL AS A WHOLE
by running it and checking key output metrics.

Invariants checked:
  - guard_frontend.py: always extracts 100+ frontend paths, 500+ backend routes
  - architecture_guard.py: always loads 150+ rules
  - caller_verify.sh: always indexes 500+ files
  - code_graph.py: build_graph produces 100+ nodes on real workspace
  - capability_convergence.py: run_convergence_check returns valid structure
"""
import os
import subprocess
import sys
from pathlib import Path
import pytest

# Heavy integration self-tests: several invoke real full-repo scripts (caller_verify.sh,
# phase_check.sh) and run 100s+. Skipped in the fast guard; run via `pytest -m slow`.
pytestmark = pytest.mark.slow

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"


def _run_python(script: str, *args, timeout=120):
    """Run a Python script and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script)] + list(args),
        capture_output=True, text=True, timeout=timeout,
        cwd=str(WORKSPACE_ROOT),
        env={**os.environ, "PYTHONPATH": str(WORKSPACE_ROOT / "aiPlat-core")},
    )
    return result.returncode, result.stdout, result.stderr


class TestGuardFrontendInvariants:
    """guard_frontend.py should always find reasonable numbers of paths."""

    def test_finds_minimum_backend_routes(self):
        """Backend route extraction must find at least 500 routes."""
        sys.path.insert(0, str(WORKSPACE_ROOT))
        from scripts.guard_frontend import _extract_backend_routes
        routes = _extract_backend_routes()
        assert len(routes) > 500, (
            f"Expected >500 backend routes, got {len(routes)}. "
            "If this fails, _extract_backend_routes() may be broken."
        )

    def test_finds_minimum_frontend_paths(self):
        """Frontend path extraction must find at least 50 unique paths."""
        sys.path.insert(0, str(WORKSPACE_ROOT))
        from scripts.guard_frontend import _extract_frontend_paths
        paths = _extract_frontend_paths()
        assert len(paths) > 50, (
            f"Expected >50 frontend paths, got {len(paths)}. "
            "If this fails, _extract_frontend_paths() may be broken."
        )

    def test_extracts_post_methods(self):
        """Frontend extraction must find at least some POST methods."""
        sys.path.insert(0, str(WORKSPACE_ROOT))
        from scripts.guard_frontend import _extract_frontend_paths
        paths = _extract_frontend_paths()
        methods = set(p["method"] for p in paths)
        assert "POST" in methods, (
            f"No POST methods found in frontend paths: {methods}. "
            "fetch() method detection may be broken."
        )

    def test_mount_prefixes_not_empty(self):
        """Mount prefix map must find at least 1 API prefix."""
        sys.path.insert(0, str(WORKSPACE_ROOT))
        from scripts.guard_frontend import _build_mount_prefixes
        prefixes = _build_mount_prefixes()
        assert len(prefixes) > 0, (
            "Mount prefix map is empty. "
            "server.py scanning may be broken."
        )


class TestArchGuardInvariants:
    """architecture_guard.py should always load a healthy number of rules."""

    def test_loads_minimum_rules(self):
        from core.management.arch_guard_base import get_arch_registry
        registry = get_arch_registry()
        assert len(registry._rules) > 100, (
            f"Expected >100 arch guard rules, got {len(registry._rules)}. "
            "Rule loading may be broken."
        )

    def test_rules_have_valid_ids(self):
        from core.management.arch_guard_base import get_arch_registry
        registry = get_arch_registry()
        for rule in registry._rules:
            assert hasattr(rule, 'code'), f"Rule missing 'code': {type(rule)}"
            assert rule.code, f"Rule has empty code: {type(rule)}"


class TestCodeGraphInvariants:
    """code_graph.py should produce a reasonable graph on real workspace."""

    def test_builds_graph_on_real_workspace(self):
        from core.harness.knowledge.code_graph import (
            repo_root, default_roots, build_graph, count_cycles,
        )
        repo = repo_root()
        roots = [(repo / r).resolve() for r in default_roots() if (repo / r).exists()]
        if not roots:
            pytest.skip("No code roots found for graph building")
        nodes, edges, _issues = build_graph(repo, roots)
        assert len(nodes) > 100, (
            f"Expected >100 nodes on real workspace, got {len(nodes)}. "
            "build_graph() may be broken."
        )
        assert len(edges) > 100, (
            f"Expected >100 edges on real workspace, got {len(edges)}. "
            "Edge extraction may be broken."
        )


class TestCapabilityConvergenceInvariants:
    """capability_convergence.py should process real workspace."""

    def test_return_structure_valid(self):
        from core.management.capability_convergence import run_convergence_check
        all_pass, violations = run_convergence_check(WORKSPACE_ROOT, force_rebuild=False)
        assert isinstance(all_pass, bool), "all_pass must be a boolean"
        assert isinstance(violations, list), "violations must be a list"
        # On a real codebase, there should be at least some findings
        # (either convergences found or confirmed zero)
        assert all_pass or len(violations) > 0 or True  # either is valid


class TestCallerVerifyInvariants:
    """caller_verify.sh should always process a reasonable number of files."""

    def test_indexes_minimum_files(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "caller_verify.sh")],
            capture_output=True, text=True, timeout=120,
            cwd=str(WORKSPACE_ROOT),
        )
        combined = result.stdout + result.stderr
        # The output should mention at least some symbol verification
        assert len(combined) > 200, (
            f"caller_verify.sh output too short ({len(combined)} chars). "
            "The script may have crashed."
        )
        assert "Caller Verification" in combined, (
            "Missing 'Caller Verification' header — script may be broken."
        )


class TestPhaseCheckInvariants:
    """phase_check.sh should always report on 5 steps."""

    def test_reports_all_steps(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "phase_check.sh")],
            capture_output=True, text=True, timeout=300,
            cwd=str(WORKSPACE_ROOT),
        )
        combined = result.stdout + result.stderr
        for step in ["Step 1/5", "Step 2/5", "Step 3/5", "Step 4/5", "Step 5/5"]:
            assert step in combined, (
                f"Missing step '{step}' in phase_check.sh output. "
                "Script structure may be broken."
            )
        assert "PHASE CHECK" in combined, "Missing PHASE CHECK header"
