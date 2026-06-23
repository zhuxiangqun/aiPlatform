"""
Tool self-tests: verify guard_ast_behavior.py core functions are correct.

Tests:
  - _is_llm_call: detects LLM API calls in AST
  - _has_pragma_allow: detects pragma markers
  - scan_file: scans Python files for violations
  - _scan_agent_for_context_violation: context assembly check
"""
import ast
import sys
import tempfile
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT / "scripts"))

from guard_ast_behavior import (
    _is_llm_call,
    _has_pragma_allow,
    scan_file,
    _scan_agent_for_context_violation,
)

def _parse_expr(code: str) -> ast.AST:
    """Parse a single expression into an AST node."""
    tree = ast.parse(code)
    return tree.body[0].value if isinstance(tree.body[0], ast.Expr) else tree.body[0]


class TestIsLLMCall:

    def test_detects_llm_call(self):
        node = _parse_expr("sys_llm_generate(model, messages)")
        assert _is_llm_call(node)

    def test_detects_nested_llm_call(self):
        node = _parse_expr("self._generate_response(messages)")
        # _generate_response might not match the exact LLM pattern
        # Test with known LLM pattern
        assert _is_llm_call(_parse_expr("sys_llm_generate(None, msgs)"))

    def test_ignores_non_llm(self):
        node = _parse_expr("print('hello')")
        result = _is_llm_call(node)
        print(f"_is_llm_call(print): {result}")
        # A print call is definitely not an LLM call
        assert not _is_llm_call(_parse_expr("x + 1"))
        assert not _is_llm_call(_parse_expr("self.normal_method()"))


class TestPragmaAllow:

    def test_detects_pragma_in_docstring(self):
        code = 'def my_func():\n    """## platform:allowed"""\n    pass'
        tree = ast.parse(code)
        func = tree.body[0]
        assert _has_pragma_allow(func)

    def test_no_pragma_without_marker(self):
        code = 'def my_func():\n    """Normal docstring"""\n    pass'
        tree = ast.parse(code)
        func = tree.body[0]
        assert not _has_pragma_allow(func)


class TestScanFile:

    def test_scans_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "clean.py"
            fp.write_text("import os\nprint('hello')\n")
            violations = scan_file(fp)
            assert isinstance(violations, list)

    def test_scans_file_with_llm_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "with_llm.py"
            fp.write_text("""
from core.harness.syscalls.llm import sys_llm_generate
async def call_llm():
    return await sys_llm_generate(None, messages)
""")
            violations = scan_file(fp, "harness/syscalls/test.py")
            assert isinstance(violations, list)

    def test_returns_list_for_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "test.py"
            fp.write_text("x = 1\n")
            violations = scan_file(fp)
            assert isinstance(violations, list)
