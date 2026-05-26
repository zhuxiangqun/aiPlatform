"""
sys_code_intel_context — Code intelligence context for Agents.

Before exploring a codebase, Agents call this to get pre-built dependency
graph info: relevant files, imports, health score, blast radius.

Replaces the grep/glob/read exploration loop with a single indexed query.
"""

from __future__ import annotations

from typing import Any, Dict, List


def sys_code_intel_context(task: str, *, roots: List[str] = None) -> Dict[str, Any]:
    u"""Return context-relevant code graph data for a given development task.

    Uses the pre-built code dependency graph (core/harness/knowledge/code_graph.py)
    to answer "where should I start" without spawning Explore sub-agents.

    Returns: {task, stats, health, related: [{file, imports}]}
    """
    from core.harness.knowledge.code_graph import build_context
    return build_context(task, roots)


def sys_code_intel_blast(file_path: str) -> List[str]:
    u"""Return the forward blast radius of a file (all files reachable via imports)."""
    from core.harness.knowledge.code_graph import repo_root, default_roots, build_graph, blast
    _repo_root = repo_root()
    roots = default_roots()
    abs_roots = [(_repo_root / r).resolve() for r in roots]
    nodes, _, _ = build_graph(_repo_root, abs_roots)
    if file_path not in nodes:
        return []
    return blast(nodes, file_path)
