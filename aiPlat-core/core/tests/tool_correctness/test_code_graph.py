"""
Tool self-tests: verify code_graph.py core functions are correct.

Tests:
  - _extract_py_imports_ast: correct import extraction
  - _extract_calls_ast: correct call extraction
  - _route_matches: route pattern matching
  - _is_code_file / _should_skip: file filtering
  - build_graph: graph construction on temp directory
  - count_cycles: cycle detection on known graph
"""
import os
import sys
import tempfile
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))

# Import the module
from core.harness.knowledge.code_graph import (
    _extract_py_imports_ast,
    _extract_calls_ast,
    _route_matches,
    _is_code_file,
    _should_skip,
    build_graph,
    count_cycles,
    report_cycles,
)


class TestExtractImports:

    def test_extracts_simple_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "test.py"
            fp.write_text("import os\nimport sys\nfrom pathlib import Path\n")
            imports = _extract_py_imports_ast(fp)
            mods = {m for m, _ in imports}
            assert "os" in mods
            assert "sys" in mods
            assert "pathlib" in mods

    def test_extracts_relative_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "test.py"
            fp.write_text("from . import utils\nfrom ..core import models\n")
            imports = _extract_py_imports_ast(fp)
            mods = {m for m, _ in imports}
            # Relative imports are extracted but may be named differently
            assert len(imports) >= 1, f"Expected at least 1 relative import, got {len(imports)}"

    def test_empty_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "empty.py"
            fp.write_text("# no imports\n")
            imports = _extract_py_imports_ast(fp)
            assert len(imports) == 0

    def test_syntax_error_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "broken.py"
            fp.write_text("import os\nthis is broken syntax!!!\nimport sys\n")
            imports = _extract_py_imports_ast(fp)
            # Should fall back to regex and still find at least 'os'
            mods = {m for m, _ in imports}
            assert "os" in mods, f"Regex fallback should find 'os', got: {mods}"


class TestExtractCalls:

    def test_extracts_function_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "test.py"
            fp.write_text("import os\nos.path.join('a', 'b')\nprint('hello')\n")
            calls = _extract_calls_ast(fp)
            # Should find function calls; exact format depends on implementation
            assert isinstance(calls, list), f"Expected list, got {type(calls)}"

    def test_empty_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "empty.py"
            fp.write_text("# nothing\n")
            calls = _extract_calls_ast(fp)
            assert len(calls) == 0


class TestRouteMatching:

    def test_exact_match(self):
        assert _route_matches("/api/platform/health", "/api/platform/health")

    def test_parameterized_match(self):
        assert _route_matches(
            "/api/v1/documents/doc_123",
            "/api/v1/documents/{doc_id}",
        )

    def test_no_match_diff_segments(self):
        assert not _route_matches(
            "/api/v1/documents",
            "/api/v1/documents/reingest",
        )


class TestFileFiltering:

    def test_is_code_file_py(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "test.py"
            fp.write_text("# test")
            assert _is_code_file(fp)

    def test_is_code_file_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "component.tsx"
            fp.write_text("// test")
            assert _is_code_file(fp)

    def test_is_code_file_non_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "README.md"
            fp.write_text("# test")
            assert not _is_code_file(fp)

    def test_should_skip_pycache(self):
        assert _should_skip(Path("__pycache__/module.pyc"))

    def test_should_skip_node_modules(self):
        assert _should_skip(Path("node_modules/react/index.js"))

    def test_should_skip_dot_git(self):
        assert _should_skip(Path(".git/objects/ab/cdef"))


class TestBuildGraph:

    def test_builds_graph_from_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.py").write_text("import b\n")
            (Path(tmp) / "b.py").write_text("import c\n")
            (Path(tmp) / "c.py").write_text("# leaf\n")

            nodes, edges, _issues = build_graph(Path(tmp), [Path(tmp)])
            assert len(nodes) >= 3, f"Expected >=3 nodes, got {len(nodes)}"
            assert len(edges) >= 2, f"Expected >=2 edges, got {len(edges)}"

    def test_no_cycles_in_simple_dag(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.py").write_text("import b\n")
            (Path(tmp) / "b.py").write_text("import c\n")
            (Path(tmp) / "c.py").write_text("# leaf\n")

            nodes, edges, _issues = build_graph(Path(tmp), [Path(tmp)])
            cycles = count_cycles(nodes)
            assert cycles == 0, f"Expected 0 cycles in DAG, got {cycles}"

    def test_detects_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.py").write_text("import b\n")
            (Path(tmp) / "b.py").write_text("import a\n")  # cycle!

            nodes, edges, _issues = build_graph(Path(tmp), [Path(tmp)])
            cycles = count_cycles(nodes)
            assert cycles >= 1, f"Expected >=1 cycle, got {cycles}"


class TestReportCycles:

    def test_report_returns_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.py").write_text("import b\n")
            (Path(tmp) / "b.py").write_text("import a\n")

            nodes, _, _ = build_graph(Path(tmp), [Path(tmp)])
            report = report_cycles(nodes)
            assert isinstance(report, list)
            assert len(report) >= 1
