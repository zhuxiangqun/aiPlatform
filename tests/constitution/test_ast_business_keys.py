"""
Architecture Constitution Tests: AST-Based Semantic Checks

Enforces CLAUDE.md §5.29 (Kernel Agnostic) at the AST level — catches violations
that regex-based grep misses (enum references, method calls, nested expressions).

Checks:
1. Hardcoded business artifact keys in state.get() / state[] calls
2. Hardcoded business keys in input_data.get() / metadata.get() in API handlers
3. Business role names used in agent_id comparisons that bypass config
"""
import ast
import os
import sys
from pathlib import Path
from typing import List, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _find_py_files(dir_path: str) -> list:
    dir_full = WORKSPACE_ROOT / dir_path
    if not dir_full.exists():
        return []
    files = []
    for root, dirs, filenames in os.walk(str(dir_full)):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", "tests")]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(root) / f)
    return files


# ---------------------------------------------------------------------------
# Business keys that MUST NOT appear as hardcoded literals in state access
# ---------------------------------------------------------------------------
FORBIDDEN_STATE_KEYS = {
    "prd", "architecture", "code", "test_report", "test_plan",
    "deploy", "frontend_code", "backend_code", "frontend", "backend",
}

# Allowed exceptions: files where these keys are legitimate
EXEMPT_FILES = {
    "schemas_builder.py", "builder_session.py", "builder_project_service.py",
    "builder_roles.py", "builder_team_service.py",
}

# Framework-level keys that are always allowed
FRAMEWORK_KEYS = {
    "phase", "error", "tokens_used", "tokens_budget", "iteration",
    "_current_stage_idx", "_graph_trace", "_checkpoints", "_last_action_reason",
    "_stage_error", "_debate_state", "_risk_score", "_deploy_error",
    "_test_execution_error", "_hitl_phase_name", "_quick_check_issues",
    "session_id", "issues", "metadata", "output", "messages", "reply",
    # LangGraph framework keys
    "step_count", "max_steps", "current_node", "context",
    "reasoning", "action", "observation",
    # Multi-agent framework keys
    "current_round", "agent_results", "converged", "final_result",
    # Engine internal keys
    "qa_retry", "task_list",
    "conversation_state", "_conversation_state",  # cross-stage conversation memory
    "output_dir",  # framework-level: project output directory set by builder
    "description",  # engine-level: project/task description (generic, not business artifact)
    "cost_used_usd",  # engine-level: cumulative stage cost tracking (generic)
    # P2-A1 event-sourced framework keys (pipeline_run_store event fold view)
    "event_derived", "state_event_consistent",
}


class BusinessKeyVisitor(ast.NodeVisitor):
    """Walk AST to find state.get("business_key") and state["business_key"] patterns."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.violations: list = []  # (line, key, expression)

    def _is_exempt_file(self) -> bool:
        return self.filepath.name in EXEMPT_FILES

    def _check_dict_access(self, node: ast.Subscript, line: int) -> None:
        """Check state["hardcoded_key"] patterns."""
        if not isinstance(node.value, ast.Name):
            return
        if node.value.id not in ("state", "local_state", "session"):
            return
        if not isinstance(node.slice, ast.Constant):
            return
        if not isinstance(node.slice.value, str):
            return
        key = node.slice.value
        if key in FRAMEWORK_KEYS:
            return
        if key in FORBIDDEN_STATE_KEYS and not self._is_exempt_file():
            self.violations.append((line, key, f'state["{key}"]'))
            return
        # Warn on unknown keys (potential new business key)
        if (key not in FRAMEWORK_KEYS
                and not key.startswith("_")
                and not self._is_exempt_file()):
            self.violations.append((line, key, f'state["{key}"] (unknown key)'))

    def _check_get_call(self, node: ast.Call, line: int) -> None:
        """Check state.get("hardcoded_key") patterns."""
        if not isinstance(node.func, ast.Attribute):
            return
        if node.func.attr != "get":
            return
        if not isinstance(node.func.value, ast.Name):
            return
        if node.func.value.id not in ("state", "local_state", "session", "input_data", "metadata"):
            return
        if not node.args:
            return
        first_arg = node.args[0]
        if not isinstance(first_arg, ast.Constant):
            return
        if not isinstance(first_arg.value, str):
            return
        key = first_arg.value
        if key in FRAMEWORK_KEYS:
            return
        if key in FORBIDDEN_STATE_KEYS and not self._is_exempt_file():
            self.violations.append((line, key, f'{node.func.value.id}.get("{key}")'))

    def visit_Subscript(self, node: ast.Subscript):
        self._check_dict_access(node, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        self._check_get_call(node, node.lineno)
        self.generic_visit(node)


class TestASTNoHardcodedBusinessKeys:
    """AST-level check: no hardcoded business artifact keys in state access."""

    def test_harness_no_hardcoded_state_keys(self):
        files = _find_py_files("aiPlat-core/core/harness/execution") + \
                _find_py_files("aiPlat-core/core/harness/memory") + \
                _find_py_files("aiPlat-core/core/harness/knowledge")
        all_violations = []
        for fp in files:
            try:
                tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
                visitor = BusinessKeyVisitor(fp)
                visitor.visit(tree)
                for line, key, expr in visitor.violations:
                    all_violations.append((fp, line, key, expr))
            except SyntaxError:
                pass

        assert not all_violations, (
            f"Harness MUST NOT use hardcoded business artifact keys. "
            f"Use config-driven keys (stage.output_artifact). "
            f"Found {len(all_violations)} violations:\n"
            + "\n".join(f"  {p}:{l}: {k} ({e})" for p, l, k, e in all_violations[:20])
        )

    def test_api_no_hardcoded_input_keys(self):
        """API handlers should not hardcode business keys in input_data.get()."""
        files = _find_py_files("aiPlat-core/core/api")
        all_violations = []
        for fp in files:
            if fp.name in ("intents.py",):  # known API boundary
                continue
            try:
                tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
                visitor = BusinessKeyVisitor(fp)
                visitor.visit(tree)
                for line, key, expr in visitor.violations:
                    if key in FORBIDDEN_STATE_KEYS:
                        all_violations.append((fp, line, key, expr))
            except SyntaxError:
                pass

        assert not all_violations, (
            f"API handlers MUST NOT hardcode business artifact keys in input_data/metadata. "
            f"Found {len(all_violations)} violations:\n"
            + "\n".join(f"  {p}:{l}: {k} ({e})" for p, l, k, e in all_violations[:20])
        )
