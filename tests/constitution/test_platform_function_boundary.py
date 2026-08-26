"""
Architecture Constitution Tests: Platform Function-Level Boundary

Enforces boundary-standard.md §铁律1 at the function level via AST analysis.
Checks that platform functions don't directly perform LLM inference
or agent discovery — these are Core responsibilities.

Authoritative reference: docs/architecture/boundary-standard.md §决策树
"""

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_DIR = WORKSPACE_ROOT / "aiPlat-platform"

# Functions that legitimately orchestrate by calling Core
# (These are platform endpoints/services, not LLM inference implementations)
ALLOWED_ORCHESTRATORS: Set[Tuple[str, str]] = {
    ("builder/builder_project_service.py", "chat"),
    ("builder/builder_project_service.py", "recommend_team"),
    ("builder/builder_project_service.py", "_semantic_output"),
    ("builder/builder_project_service.py", "start_pipeline"),
    ("builder/builder_project_service.py", "get_project_state"),
    ("builder/builder_project_service.py", "approve_stage"),
    ("builder/builder_project_service.py", "reject_stage"),
    ("builder/builder_project_service.py", "rollback_stage"),
    ("builder/builder_workflow_service.py", "execute"),
    ("builder/builder_workflow_service.py", "_nodes_to_stages"),  # execute 的辅助方法（P1-9 收敛抽取）
    ("builder/builder_session.py", "chat"),
    ("builder/builder_session.py", "create_session"),
    ("kb/intelligence/llm.py", "chat_complete"),
    ("kb/intelligence/llm.py", "llm_enabled"),
    ("kb/intelligence/summarize.py", "summarize_document"),
}

KNOWN_DEBT_FILES: Set[str] = set()

# P0-A4: business API functions that delegate LLM via CoreFacade (合规委托).
# These are platform business features (clarify/industry/prompt/eval) whose
# LLM calls go through core.api.core_facade — same as builder.chat below.
ALLOWED_LLM_ORCHESTRATORS: Set[Tuple[str, str]] = {
    ("builder/builder_project_service.py", "_extract_prd_from_chat"),
    ("builder/builder_project_service.py", "execute_skill"),
    ("apps/fde/api/fde.py", "_clarify"),
    ("apps/fde/api/fde.py", "infer_industry"),
    ("apps/fde/api/fde.py", "_extract_pending_questions"),
    ("apps/fde/api/fde.py", "fde_assess_dialog"),
    ("apps/fde/api/fde_ask.py", "fde_ask"),
    ("apps/eval/api/prompt_eval.py", "_run_evaluation"),
    ("apps/prompt/api/prompt_app.py", "preview_template"),
    ("apps/prompt/api/prompt_app.py", "preview_text"),
    ("apps/prompt/api/prompt_app.py", "run_prompt"),
    ("apps/prompt/api/prompt_app.py", "optimize_prompt"),
    ("apps/prompt/api/prompt_optimize.py", "optimize_prompt"),
}


def _get_relpath(fp: Path) -> str:
    try:
        return str(fp.relative_to(PLATFORM_DIR))
    except ValueError:
        return str(fp)


def test_platform_functions_no_llm_inference():
    """Platform functions must not directly call LLM inference APIs."""
    violations: List[str] = []
    llm_calls = {"core_chat", "ChatContext", "sys_llm_generate", "recommend_team_stages", "create_agent"}

    for fp in PLATFORM_DIR.rglob("*.py"):
        if "__pycache__" in str(fp):
            continue
        rel = _get_relpath(fp)
        if rel in KNOWN_DEBT_FILES:
            continue
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (rel, node.name) in ALLOWED_ORCHESTRATORS or (rel, node.name) in ALLOWED_LLM_ORCHESTRATORS:
                continue

            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    # Check Name calls: core_chat(...)
                    if isinstance(sub.func, ast.Name) and sub.func.id in llm_calls:
                        violations.append(f"{rel}:{node.lineno}::{node.name}() calls {sub.func.id}")
                    # Check Attribute calls: from x import y; y(...)
                    if isinstance(sub.func, ast.Attribute):
                        parts = []
                        obj = sub.func
                        while isinstance(obj, ast.Attribute):
                            parts.append(obj.attr)
                            obj = obj.value
                        if isinstance(obj, ast.Name):
                            parts.append(obj.id)
                        full = ".".join(reversed(parts))
                        for name in llm_calls:
                            if name in full:
                                violations.append(f"{rel}:{node.lineno}::{node.name}() calls {name}")

    assert not violations, (
        f"Platform has {len(violations)} function(s) performing LLM inference:\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\nLLM inference belongs in Core. Platform should delegate via CoreFacade."
        "\nReference: docs/architecture/boundary-standard.md §铁律1"
    )


def test_platform_functions_no_agent_discovery():
    """Platform functions must not perform agent catalog discovery."""
    violations: List[str] = []
    discovery_calls = {"get_agent_frontmatter", "list_available_agents", "build_agent_catalog_markdown"}

    for fp in PLATFORM_DIR.rglob("*.py"):
        if "__pycache__" in str(fp):
            continue
        rel = _get_relpath(fp)
        if rel in KNOWN_DEBT_FILES:
            continue
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (rel, node.name) in ALLOWED_ORCHESTRATORS or (rel, node.name) in ALLOWED_LLM_ORCHESTRATORS:
                continue

            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    if isinstance(sub.func, ast.Name) and sub.func.id in discovery_calls:
                        violations.append(f"{rel}:{node.lineno}::{node.name}() calls {sub.func.id}")
                    if isinstance(sub.func, ast.Attribute):
                        parts = []
                        obj = sub.func
                        while isinstance(obj, ast.Attribute):
                            parts.append(obj.attr)
                            obj = obj.value
                        if isinstance(obj, ast.Name):
                            parts.append(obj.id)
                        full = ".".join(reversed(parts))
                        for name in discovery_calls:
                            if name in full:
                                violations.append(f"{rel}:{node.lineno}::{node.name}() calls {name}")

    assert not violations, (
        f"Platform has {len(violations)} function(s) performing agent discovery:\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\nAgent discovery belongs in Core per boundary-standard.md §决策树."
        "\nReference: docs/architecture/boundary-standard.md §铁律2"
    )
