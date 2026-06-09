"""
test_prompt_loading — verify all LLM call sites in routers/apps use prompt_loader.

Enforces CLAUDE.md §5.35: "All multi-line LLM prompts MUST go through prompt_loader."

Checks:
  1. No multi-line Chinese/English prompt strings in router/apps code
     (these must be registered in prompt_loader via _register())
  2. All sys_llm_generate calls with system role must resolve via
     _async_prompt_resolve / _sync_resolve (not inline string)
"""

import ast
import os
import sys
from pathlib import Path


# ── Config ───────────────────────────────────────────────────

SCAN_DIRS = [
    "core/api/routers",
    "core/apps",
]

EXCLUDE_FILES = {
    "prompt_loader.py",
    "prompt_app.py",
    "__init__.py",
    # Class defaults (already registered as prompt_loader templates)
    "conversational.py",
    # Programmatic fallback strings (not LLM prompts)
    "multi_agent.py",
}

EXCLUDE_DIRS = {
    "__pycache__",
    "tests",
    ".git",
}

# Multi-line prompt start patterns (Chinese + English)
PROMPT_START_PATTERNS = [
    "\u4f60\u662f",       # 你是
    "\u4f60\u662f\u4e00",  # 你是一
    "\u60a8\u662f",        # 您是
    "You are a",
    "You are an",
]


# ── Helpers ───────────────────────────────────────────────────

def _is_in_excluded(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    if path.name in EXCLUDE_FILES:
        return True
    return False


def _contains_prompt_loader_call(node: ast.AST) -> bool:
    """Check if AST subtree contains _async_prompt_resolve or _sync_resolve call."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                if child.func.id in ("_async_prompt_resolve", "_sync_resolve"):
                    return True
            elif isinstance(child.func, ast.Attribute):
                if child.func.attr in ("_async_prompt_resolve", "_sync_resolve"):
                    return True
    return False


def _has_hardcoded_multi_line_prompt(file_path: Path) -> list[str]:
    """Check if file contains multi-line Chinese/English prompt strings.

    Returns list of violation line descriptions.
    """
    violations = []
    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception:
        return violations

    # Check for f-string or regular multi-line string patterns
    lines = source.split("\n")
    in_multi_string = False
    string_start = 0
    string_content = ""

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detect start of multi-line prompt: assigned or dict value with "你/You are"
        for pat in PROMPT_START_PATTERNS:
            if pat in line and ("=" in line or ":" in line):
                # Check if it's a function call argument (not a variable in prompt_loader)
                if "_async_prompt_resolve" in line or "_sync_resolve" in line:
                    continue
                if "prompt_loader" in line:
                    continue
                if "_register(" in line:
                    continue
                violations.append(f"L{i}: hardcoded prompt — use _async_prompt_resolve()")
                break

    return violations


def _check_llm_calls_use_prompt_loader(file_path: Path) -> list[str]:
    """Check that sys_llm_generate calls use prompt_loader for system prompt.

    Returns list of violation descriptions.
    """
    violations = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return violations

    class LLMCallVisitor(ast.NodeVisitor):
        def __init__(self):
            self.violations = []

        def visit_Call(self, node):
            # Detect sys_llm_generate(...) calls
            if isinstance(node.func, ast.Name) and node.func.id == "sys_llm_generate":
                pass  # continue checking
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "sys_llm_generate":
                pass
            else:
                self.generic_visit(node)
                return

            # Check if the messages argument has inline string content
            if node.args:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        # Inline string passed directly — should use prompt_loader
                        if len(arg.value) > 40 and any(
                            pat in arg.value for pat in PROMPT_START_PATTERNS
                        ):
                            if not _contains_prompt_loader_call(node):
                                self.violations.append(
                                    f"L{node.lineno}: inline prompt in sys_llm_generate — "
                                    f"use _async_prompt_resolve()"
                                )

            # Check list/dict literals for inline prompt strings
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    if len(child.value) > 40 and any(
                        pat in child.value for pat in PROMPT_START_PATTERNS
                    ):
                        if not _contains_prompt_loader_call(node):
                            self.violations.append(
                                f"L{child.lineno}: inline prompt in sys_llm_generate — "
                                f"use _async_prompt_resolve()"
                            )

            self.generic_visit(node)

    visitor = LLMCallVisitor()
    visitor.visit(tree)
    return visitor.violations


# ── Test Cases ────────────────────────────────────────────────

def test_no_hardcoded_prompts_in_routers_apps():
    """Verify no multi-line Chinese/English prompts are hardcoded in router/apps code."""
    base = Path(__file__).resolve().parent.parent.parent.parent
    violations = []

    for scan_dir in SCAN_DIRS:
        dir_path = base / scan_dir
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            if _is_in_excluded(py_file):
                continue
            file_violations = _has_hardcoded_multi_line_prompt(py_file)
            for v in file_violations:
                violations.append(f"{py_file.relative_to(base)}: {v}")

    # Assert no violations
    assert len(violations) == 0, (
        f"Found {len(violations)} hardcoded prompt(s):\n" +
        "\n".join(violations[:10]) +
        ("\n  ... and more" if len(violations) > 10 else "")
    )


def test_sys_llm_generate_uses_prompt_loader():
    """Verify sys_llm_generate calls with prompts use prompt_loader for resolution."""
    base = Path(__file__).resolve().parent.parent.parent.parent
    violations = []

    for scan_dir in SCAN_DIRS:
        dir_path = base / scan_dir
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            if _is_in_excluded(py_file):
                continue
            file_violations = _check_llm_calls_use_prompt_loader(py_file)
            for v in file_violations:
                violations.append(f"{py_file.relative_to(base)}: {v}")

    assert len(violations) == 0, (
        f"Found {len(violations)} sys_llm_generate call(s) with inline prompts:\n" +
        "\n".join(violations[:10]) +
        ("\n  ... and more" if len(violations) > 10 else "")
    )
