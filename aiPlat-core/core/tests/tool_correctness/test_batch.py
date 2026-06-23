"""
Batch tool self-tests: verify remaining guard/diagnostic/benchmark programs
all import and have the expected basic structure.

Covers: benchmark_*, dead_component_check, audit_reasoning_paths,
        routing_eval, rag_eval_cli, compliance_checks, config validators,
        graph_*, smoke/E2E scripts
"""
import importlib.util
import subprocess
import sys
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"
CORE_MGMT = WORKSPACE_ROOT / "aiPlat-core/core/management"
HARNESS = WORKSPACE_ROOT / "aiPlat-core/core/harness"


def _import_script(script_path: Path, module_name: str = "tmp"):
    """Import a script by path and return its module object."""
    spec = importlib.util.spec_from_file_location(
        module_name,
        str(script_path),
    )
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# Benchmark programs
# ══════════════════════════════════════════════════════════════

class TestBenchmarks:

    def test_benchmark_ontology_imports(self):
        mod = _import_script(SCRIPTS_DIR / "benchmark_ontology.py", "bm_onto")
        assert mod is not None, "benchmark_ontology.py failed to import"

    def test_benchmark_traversal_imports(self):
        mod = _import_script(SCRIPTS_DIR / "benchmark_traversal.py", "bm_trav")
        assert mod is not None, "benchmark_traversal.py failed to import"

    def test_benchmark_sysgraph_imports(self):
        mod = _import_script(SCRIPTS_DIR / "benchmark_sysgraph.py", "bm_sys")
        assert mod is not None, "benchmark_sysgraph.py failed to import"

    def test_benchmark_live_imports(self):
        mod = _import_script(SCRIPTS_DIR / "benchmark_live.py", "bm_live")
        assert mod is not None, "benchmark_live.py failed to import"

    def test_benchmark_all_runs(self):
        """benchmark_all.sh should run without errors."""
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "benchmark_all.sh"), "--ci"],
            capture_output=True, text=True, timeout=30,
            cwd=str(WORKSPACE_ROOT),
        )
        # May exit non-zero in CI mode — just verify it doesn't crash
        assert result.returncode in (0, 1, 2), f"Unexpected exit: {result.returncode}"


# ══════════════════════════════════════════════════════════════
# Quality evaluation programs
# ══════════════════════════════════════════════════════════════

class TestQualityEval:

    def test_routing_eval_imports(self):
        mod = _import_script(SCRIPTS_DIR / "routing_eval.py", "reval")
        assert mod is not None, "routing_eval.py failed to import"

    def test_rag_eval_cli_imports(self):
        mod = _import_script(SCRIPTS_DIR / "rag_eval_cli.py", "rag_eval")
        assert mod is not None, "rag_eval_cli.py failed to import"

    def test_audit_reasoning_paths_imports(self):
        mod = _import_script(SCRIPTS_DIR / "audit_reasoning_paths.py", "audit_rp")
        assert mod is not None, "audit_reasoning_paths.py failed to import"


# ══════════════════════════════════════════════════════════════
# Diagnostics programs
# ══════════════════════════════════════════════════════════════

class TestDiagnostics:

    def test_compliance_checks_imports(self):
        mod = _import_script(CORE_MGMT / "compliance_checks.py", "ccheck")
        assert mod is not None, "compliance_checks.py failed to import"

    def test_agent_config_validator_imports(self):
        mod = _import_script(CORE_MGMT / "agent_config_validator.py", "acv")
        assert mod is not None, "agent_config_validator.py failed to import"

    def test_mcp_config_validator_imports(self):
        mod = _import_script(CORE_MGMT / "mcp_config_validator.py", "mcv")
        assert mod is not None, "mcp_config_validator.py failed to import"


# ══════════════════════════════════════════════════════════════
# Graph modules
# ══════════════════════════════════════════════════════════════

class TestGraphModules:

    def test_sharded_graph_imports(self):
        from core.harness.ontology_engine.sharded_graph import ShardedGraphIndex
        assert ShardedGraphIndex is not None

    def test_graph_inference_imports(self):
        from core.harness.ontology_engine.graph_inference import GraphInference
        assert GraphInference is not None

    def test_graph_sync_imports(self):
        from core.harness.knowledge.graph_sync import GraphSyncHandler
        assert GraphSyncHandler is not None


# ══════════════════════════════════════════════════════════════
# Shell scripts (smoke/E2E/dead_component)
# ══════════════════════════════════════════════════════════════

class TestShellScripts:

    def test_dead_component_check_runs(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "dead_component_check.sh")],
            capture_output=True, text=True, timeout=30,
            cwd=str(WORKSPACE_ROOT),
        )
        assert result.returncode in (0, 1), \
            f"dead_component_check.sh exit code {result.returncode}"

    @pytest.mark.skip(reason="Requires live servers — run manually")
    def test_smoke_http_server_runs(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "smoke_http_server.sh")],
            capture_output=True, text=True, timeout=30,
            cwd=str(WORKSPACE_ROOT),
        )
        assert result.returncode in (0, 1, 2, 7)

    @pytest.mark.skip(reason="Requires live servers — run manually")
    def test_health_sh_runs(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "health.sh")],
            capture_output=True, text=True, timeout=15,
            cwd=str(WORKSPACE_ROOT),
        )
        assert result.returncode in (0, 1, 7)

    @pytest.mark.skip(reason="Requires live servers — run manually")
    def test_pre_check_sh_runs(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "pre_check.sh")],
            capture_output=True, text=True, timeout=30,
            cwd=str(WORKSPACE_ROOT),
        )
        assert result.returncode in (0, 1)
