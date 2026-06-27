#!/usr/bin/env python3
"""
AST Behavior Guard — detects functions that perform LLM inference
without proper context management, and platform boundary violations.

Scans:
  - aiPlat-platform/**/*.py           (boundary-standard.md §铁律1)
  - aiPlat-core/core/apps/agents/**/*.py  (§7 context assembly)

Checks:
  - platform: core_chat/ChatContext/create_agent/sys_llm_generate calls
  - platform: glob/open AGENT.md patterns
  - agents: execute() using sys_llm_generate without build_context/MemoryManager
"""

import ast
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_DIR = WORKSPACE_ROOT / "aiPlat-platform"
CORE_AGENTS_DIR = WORKSPACE_ROOT / "aiPlat-core" / "core" / "apps" / "agents"

# Silent except:pass baseline ratchet (§5.68/§25): forbid NEW silent error-swallowing.
# Existing 1900+ are tracked as a baseline; CI fails only if the count INCREASES.
SILENT_EXCEPT_ROOTS = ["aiPlat-core", "aiPlat-platform", "aiPlat-infra", "aiPlat-app", "aiPlat-management"]
SILENT_EXCEPT_BASELINE = WORKSPACE_ROOT / "scripts" / "baselines" / "silent_except_baseline.txt"
SILENT_EXCEPT_SKIP = ("__pycache__", "/tests/", "/test_", "/.venv/", "node_modules", "/generated/")

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


# ── §7: Context assembly compliance ──────────────────────────────────────

CONTEXT_MGMT_CALLS = {
    "build_context",         # MemoryManager.build_context()
    "_maybe_compact_messages",  # loop._maybe_compact_messages()
    "compact_context",       # generic compact
    "compress_retrieved_docs",  # doc_compressor
}


def _is_context_mgmt_call(node: ast.AST) -> bool:
    """Check if AST node is a call to a context management function."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name) and node.func.id in CONTEXT_MGMT_CALLS:
        return True
    if isinstance(node.func, ast.Attribute):
        full = _get_attribute_name(node.func)
        return any(c in full for c in CONTEXT_MGMT_CALLS)
    return False


def _scan_agent_for_context_violation(filepath: Path, rel_path: str) -> List[Dict]:
    """Check agent execute() methods: if they use sys_llm_generate,
    they MUST also use context management (build_context/MemoryManager)."""
    # base.py goes through ReActLoop which calls build_context internally
    # materials_chat.py is kept for backward compat (v4.0 PipelineAgent replaces it)
    # pipeline_agent.py delegates to BaseAgent.execute() → ReActLoop
    if filepath.name in ("base.py", "materials_chat.py", "pipeline_agent.py"):
        return []
    violations = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Focus on execute() and _execute_impl() methods
        if node.name not in ("execute", "_execute_impl"):
            continue

        has_llm = False
        has_context_mgmt = False
        for sub in ast.walk(node):
            if _is_llm_call(sub):
                has_llm = True
            if _is_context_mgmt_call(sub):
                has_context_mgmt = True

        if has_llm and not has_context_mgmt:
            violations.append({
                "function": node.name,
                "line": node.lineno,
                "reason": "calls sys_llm_generate without build_context/MemoryManager (bypasses 5-level compression)",
            })

    return violations


def scan_core_agents() -> Dict[str, List[Dict]]:
    """Scan core agent Python files for context assembly compliance."""
    results: Dict[str, List[Dict]] = {}
    if not CORE_AGENTS_DIR.exists():
        return results

    for fp in sorted(CORE_AGENTS_DIR.rglob("*.py")):
        if "__pycache__" in str(fp):
            continue
        rel = str(fp.relative_to(CORE_AGENTS_DIR))
        v = _scan_agent_for_context_violation(fp, rel_path=rel)
        if v:
            results[rel] = v
    return results


def _is_in_safe_ast_context(filepath: Path, target_line: int) -> bool:
    """Check if a given line is in a safe context for auto-fix.
    
    Safe = inside a function body, inside if __name__ == '__main__',
    or inside try/except ImportError. Returns False if AST parse fails
    (cannot determine context → block auto-fix for safety).
    
    Args:
        filepath: Path to Python file
        target_line: 1-indexed line number to check
    """
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
    except SyntaxError:
        return False  # cannot parse → block auto-fix

    target_in_safe_scope = False
    
    for node in ast.walk(tree):
        # Check if target line is inside a function body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= target_line <= node.end_lineno:
                target_in_safe_scope = True
                break

        # Check if target line is inside if __name__ == '__main__'
        if isinstance(node, ast.If):
            if (node.lineno <= target_line <= node.end_lineno and
                isinstance(node.test, ast.Compare) and
                isinstance(node.test.left, ast.Name) and
                node.test.left.id == '__name__' and
                any(isinstance(op, ast.Eq) for op in node.test.ops) and
                any(isinstance(comp, ast.Constant) and comp.value == '__main__' 
                    for comp in node.test.comparators)):
                target_in_safe_scope = True
                break

        # Check if target line is inside try/except ImportError
        if isinstance(node, ast.Try):
            if node.lineno <= target_line <= node.end_lineno:
                for handler in node.handlers:
                    if (isinstance(handler.type, ast.Name) and 
                        handler.type.id == 'ImportError'):
                        target_in_safe_scope = True
                        break

    return target_in_safe_scope


def main():
    if "--write-baseline" in sys.argv:
        count = len(scan_silent_except())
        _write_silent_baseline(count)
        print(f"PASS: silent except:pass baseline written = {count}")
        return 0

    results, pragma_warnings = scan_platform()
    agent_results = scan_core_agents()

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

    if agent_results:
        print(f"FAIL: {len(agent_results)} agent file(s) bypass context compression")
        for filepath, funcs in sorted(agent_results.items()):
            for f in funcs:
                print(f"  → {filepath}:{f['line']}::{f['function']}() — {f['reason']}")
        exit_code = 1
    else:
        print("PASS: No agent file(s) bypass context compression")

    if pragma_warnings:
        print(f"WARN: {len(pragma_warnings)} file(s) exceed pragma threshold (max 3 exemptions)")
        for w in pragma_warnings:
            print(f"  ⚠ {w}")
    else:
        print("PASS: Pragma exemption counts within threshold")

    # ── §3 extended: business role inference patterns ──
    biz_results = scan_core_business_strings()
    if biz_results:
        print(f"WARN: {len(biz_results)} core file(s) contain business role inference patterns (§5.29 v4.1)")
        for filepath, lines in sorted(biz_results.items()):
            print(f"  → {filepath}: line(s) {','.join(map(str, lines))}")
    else:
        print("PASS: No business role inference patterns in core")

    # ── Silent except:pass — baseline ratchet (forbid NEW silent swallows, §5.68/§25) ──
    silent_count = len(scan_silent_except())
    baseline = _load_silent_baseline()
    if baseline < 0:
        print(f"WARN: silent except:pass baseline not set (current={silent_count}). "
              "Run: python3 scripts/guard_ast_behavior.py --write-baseline")
    elif silent_count > baseline:
        print(f"FAIL: silent except:pass increased {baseline} → {silent_count} "
              f"(+{silent_count - baseline}). NEW silent error-swallowing forbidden (§5.68).")
        print("      Fix: add logging/raise in the new handler(s). "
              "Do NOT raise the baseline to mask new swallows.")
        exit_code = 1
    elif silent_count < baseline:
        print(f"PASS: silent except:pass {silent_count} < baseline {baseline} — ratchet down! "
              "Lock it in: python3 scripts/guard_ast_behavior.py --write-baseline")
    else:
        print(f"PASS: silent except:pass at baseline ({silent_count})")

    return exit_code


def scan_core_business_strings() -> Dict[str, List[int]]:
    """Grep-scan core/management for business role inference patterns."""
    import subprocess, os
    core_dir = WORKSPACE_ROOT / "aiPlat-core" / "core"
    mgmt_dir = core_dir / "management"
    if not mgmt_dir.exists():
        return {}

    patterns = (
        r'any\\(kw\s+in\s+_name\s+for\s+kw\s+in\s+\\[',
        r'any\\(kw\s+in\s+_desc\s+for\s+kw\s+in\s+\\[',
    )
    results: Dict[str, List[int]] = {}
    try:
        output = subprocess.check_output(
            ["grep", "-rn", "-E", "|".join(patterns), str(mgmt_dir)],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in output.strip().split("\n"):
            if not line: continue
            parts = line.split(":", 2)
            if len(parts) >= 2:
                fname = parts[0].replace(str(mgmt_dir) + "/", "")
                try:
                    line_no = int(parts[1])
                    if fname not in results:
                        results[fname] = []
                    results[fname].append(line_no)
                except ValueError:
                    pass
    except subprocess.CalledProcessError:
        pass  # grep returns 1 when no matches
    return results


def scan_silent_except() -> List[str]:
    """AST-scan for silent except handlers whose body is ONLY `pass` (no log/raise/return).

    These swallow errors at the source — the root cause of "errors that can't be traced".
    Returns sorted list of 'relpath:line' locations across all repos.
    """
    locations: List[str] = []
    for root in SILENT_EXCEPT_ROOTS:
        root_dir = WORKSPACE_ROOT / root
        if not root_dir.exists():
            continue
        for py in root_dir.rglob("*.py"):
            sp = str(py)
            if any(skip in sp for skip in SILENT_EXCEPT_SKIP):
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and all(
                    isinstance(s, ast.Pass) for s in node.body
                ):
                    rel = sp.replace(str(WORKSPACE_ROOT) + "/", "")
                    locations.append(f"{rel}:{node.lineno}")
    return sorted(locations)


def _load_silent_baseline() -> int:
    try:
        return int(SILENT_EXCEPT_BASELINE.read_text(encoding="utf-8").strip())
    except Exception:
        return -1


def _write_silent_baseline(count: int) -> None:
    SILENT_EXCEPT_BASELINE.parent.mkdir(parents=True, exist_ok=True)
    SILENT_EXCEPT_BASELINE.write_text(f"{count}\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
