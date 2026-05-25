#!/usr/bin/env python3
"""
AST Behavior Guard — detects functions in platform/ that perform
LLM inference or agent discovery (boundary-standard.md §铁律1).

Scans: aiPlat-platform/**/*.py
Checks: function bodies for core_chat/ChatContext/create_agent/sys_llm_generate calls
        AND glob/open AGENT.md patterns

Excludes:
  - api/rest/routes.py (legitimate gateway endpoints)
  - Functions with @platform_delegate decorator
  - Functions marked with ## platform:allowed pragma comment

Returns: 0 if clean, 1 if violations found
"""

import ast
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_DIR = WORKSPACE_ROOT / "aiPlat-platform"

# ── Detection rules ──────────────────────────────────────────────────────

LLM_INFERENCE_CALLS = {
    "core_chat",           # intents.core_chat()
    "ChatContext",         # intents.ChatContext instantiation
    "sys_llm_generate",    # harness syscall
    "recommend_team_stages", # team_planner (core)
    "create_agent",        # agent factory
}

AGENT_DISCOVERY_PATTERNS = {
    "get_agent_frontmatter",  # core_facade agent loader
    "list_available_agents",  # team_planner agent scanner
    "build_agent_catalog_markdown",
}

# Directories excluded from behavioral checks (legitimate orchestrators)
EXCLUDED_PATHS = {
    "api/rest/routes.py",
    "api/routers/",
}

# Functions explicitly allowed to call Core (orchestration layer)
# Keys: (file_relpath, function_name)
ALLOWED_FUNCTIONS: Set[Tuple[str, str]] = {
    # Builder — legitimate platform orchestrators
    ("builder/builder_project_service.py", "chat"),
    ("builder/builder_project_service.py", "recommend_team"),
    ("builder/builder_project_service.py", "_semantic_output"),
    ("builder/builder_project_service.py", "start_pipeline"),
    ("builder/builder_project_service.py", "get_project_state"),
    ("builder/builder_project_service.py", "approve_stage"),
    ("builder/builder_project_service.py", "reject_stage"),
    ("builder/builder_project_service.py", "rollback_stage"),
    ("builder/builder_session.py", "chat"),
    ("builder/builder_session.py", "create_session"),
    # KB — legitimate platform LLM wrappers
    ("kb/intelligence/llm.py", "chat_complete"),
    ("kb/intelligence/llm.py", "llm_enabled"),
    ("kb/intelligence/summarize.py", "summarize_document"),
}


def _is_llm_call(node: ast.AST) -> bool:
    """Check if an AST node is an LLM inference call."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in LLM_INFERENCE_CALLS:
            return True
        if isinstance(node.func, ast.Attribute):
            # Check for core_chat / ChatContext in attribute access
            parts = []
            obj = node.func
            while isinstance(obj, ast.Attribute):
                parts.append(obj.attr)
                obj = obj.value
            if isinstance(obj, ast.Name):
                parts.append(obj.id)
            full = ".".join(reversed(parts))
            for call_name in LLM_INFERENCE_CALLS:
                if call_name in full:
                    return True
    return False


def _is_agent_discovery(node: ast.AST) -> bool:
    """Check if an AST node performs agent discovery (scans AGENT.md files)."""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in AGENT_DISCOVERY_PATTERNS:
            return True
        if isinstance(node.func, ast.Attribute):
            full = _get_attribute_name(node.func)
            for name in AGENT_DISCOVERY_PATTERNS:
                if name in full:
                    return True
        # Check for glob("...agents/*/AGENT.md") patterns
        if isinstance(node.func, ast.Attribute):
            full = _get_attribute_name(node.func)
            if "glob" in full and len(node.args) > 0:
                arg = node.args[0]
                if isinstance(arg, ast.BinOp) or (isinstance(arg, ast.Constant) and "AGENT" in str(getattr(arg, "value", ""))):
                    return True
    return False


def _get_attribute_name(node: ast.Attribute) -> str:
    parts = []
    obj = node
    while isinstance(obj, ast.Attribute):
        parts.append(obj.attr)
        obj = obj.value
    if isinstance(obj, ast.Name):
        parts.append(obj.id)
    return ".".join(reversed(parts))


def _has_pragma_allow(func_node: ast.FunctionDef) -> bool:
    """Check if function has ## platform:allowed pragma in docstring or comments."""
    # Check docstring
    if (isinstance(func_node.body[0], ast.Expr) and
        isinstance(func_node.body[0].value, (ast.Constant, ast.Str))):
        doc = getattr(func_node.body[0].value, 'value', '')
        if '## platform:allowed' in str(doc):
            return True
    # Check decorators
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == 'platform_delegate':
            return True
    return False


def scan_file(filepath: Path, rel_path: str = "") -> List[Dict]:
    """Scan a single Python file for boundary violations."""
    violations = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_name = node.name

        # Whitelist check
        if (rel_path, func_name) in ALLOWED_FUNCTIONS:
            continue

        has_llm = False
        has_agent_discovery = False

        for sub in ast.walk(node):
            if _is_llm_call(sub):
                has_llm = True
            if _is_agent_discovery(sub):
                has_agent_discovery = True

        if (has_llm or has_agent_discovery) and not _has_pragma_allow(node):
            violations.append({
                "function": func_name,
                "line": node.lineno,
                "llm_inference": has_llm,
                "agent_discovery": has_agent_discovery,
            })

    return violations


def scan_platform() -> Dict[str, List[Dict]]:
    """Scan all platform Python files for boundary violations."""


def scan_platform() -> Tuple[Dict[str, List[Dict]], List[str]]:
    """Scan all platform Python files for boundary violations and pragma abuse."""
    results: Dict[str, List[Dict]] = {}
    pragma_warnings: List[str] = []

    for fp in sorted(PLATFORM_DIR.rglob("*.py")):
        if "__pycache__" in str(fp):
            continue
        rel = str(fp.relative_to(PLATFORM_DIR))

        # Skip excluded paths
        excluded = False
        for ex_path in EXCLUDED_PATHS:
            if rel.startswith(ex_path):
                excluded = True
                break
        if excluded:
            continue

        v = scan_file(fp, rel_path=rel)
        if v:
            results[rel] = v

        # Pragma abuse check: more than 3 ## platform:allowed in one file
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")
            pragma_count = content.count("## platform:allowed")
            decorator_count = content.count("@platform_delegate")
            total = pragma_count + decorator_count
            if total > 3:
                pragma_warnings.append(f"{rel}: {total} pragma exemptions (threshold=3)")
        except Exception:
            pass

    return results, pragma_warnings


def main():
    results, pragma_warnings = scan_platform()

    exit_code = 0

    if results:
        print(f"FAIL: {len(results)} platform file(s) contain LLM inference or agent discovery")
        for filepath, funcs in sorted(results.items()):
            for f in funcs:
                reasons = []
                if f["llm_inference"]:
                    reasons.append("LLM inference")
                if f["agent_discovery"]:
                    reasons.append("agent discovery")
                reason = " + ".join(reasons)
                print(f"  → {filepath}:{f['line']}::{f['function']}() — {reason}")
                print(f"     (add ## platform:allowed pragma or @platform_delegate decorator to whitelist)")
        exit_code = 1
    else:
        print("PASS: No platform functions perform LLM inference or agent discovery")

    if pragma_warnings:
        print(f"WARN: {len(pragma_warnings)} file(s) exceed pragma threshold (max 3 exemptions)")
        for w in pragma_warnings:
            print(f"  ⚠ {w}")
        # Don't fail, just warn
    else:
        print("PASS: Pragma exemption counts within threshold")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
