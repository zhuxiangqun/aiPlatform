"""
AST Graph Diff — semantic-level code change detection.

Detects structural changes by parsing code into AST and computing
graph-level differences, going beyond text-level diff to identify
meaningful semantic changes.

Level 1 (text): variable renamed
Level 2 (AST): function signature unchanged, internal loop added
Level 3 (semantic): loop introduces O(n²)

Leverages Python's built-in ast module for zero-dependency analysis.
"""

from __future__ import annotations

import ast
import os
from typing import Any, Dict, List, Optional, Set


def parse_code_to_graph(code: str) -> Dict[str, Any]:
    """Parse Python source code into a structural graph representation.

    Returns dict with: nodes (list of {type, name, line, children}),
    edges (list of {from, to, relation}), functions, classes, imports.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"nodes": [], "edges": [], "error": "syntax_error"}

    nodes: List[Dict] = []
    edges: List[Dict] = []
    functions: List[str] = []
    classes: List[str] = []
    imports: List[str] = []
    node_id = 0

    def _add_node(node_type: str, name: str, lineno: int) -> int:
        nonlocal node_id
        nid = node_id
        node_id += 1
        nodes.append({"id": nid, "type": node_type, "name": name, "line": lineno})
        return nid

    root_id = _add_node("module", "<module>", 0)

    for item in ast.walk(tree):
        if isinstance(item, ast.FunctionDef):
            fid = _add_node("function", item.name, item.lineno)
            edges.append({"from": root_id, "to": fid, "relation": "contains"})
            functions.append(item.name)
            if item.args:
                for arg in item.args.args:
                    aid = _add_node("argument", arg.arg, item.lineno)
                    edges.append({"from": fid, "to": aid, "relation": "param"})
            if item.returns:
                rid = _add_node("return_type", ast.dump(item.returns), item.lineno)
                edges.append({"from": fid, "to": rid, "relation": "returns"})
        elif isinstance(item, ast.ClassDef):
            cid = _add_node("class", item.name, item.lineno)
            edges.append({"from": root_id, "to": cid, "relation": "contains"})
            classes.append(item.name)
        elif isinstance(item, (ast.Import, ast.ImportFrom)):
            for alias in item.names:
                imports.append(alias.name)
        elif isinstance(item, (ast.For, ast.While)):
            _add_node("loop", type(item).__name__, item.lineno)
        elif isinstance(item, ast.Try):
            _add_node("try_block", "try", item.lineno)
        elif isinstance(item, ast.Raise):
            _add_node("raise", "raise", item.lineno)

    return {
        "nodes": nodes,
        "edges": edges,
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def diff_graphs(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute semantic diff between two code graph representations.

    Returns changes organized by category:
    - added_functions, removed_functions, changed_functions
    - added_imports, removed_imports
    - added_classes, removed_classes
    - structural_changes: loop/try/raise nodes added/removed
    - verdict: "unchanged" | "minor" | "structural" | "major"
    """
    b_funcs = set(before.get("functions", []))
    a_funcs = set(after.get("functions", []))
    b_imports = set(before.get("imports", []))
    a_imports = set(after.get("imports", []))
    b_classes = set(before.get("classes", []))
    a_classes = set(after.get("classes", []))

    b_types = Counter(n.get("type", "") for n in before.get("nodes", []))
    a_types = Counter(n.get("type", "") for n in after.get("nodes", []))

    added_funcs = sorted(a_funcs - b_funcs)
    removed_funcs = sorted(b_funcs - a_funcs)
    added_imports = sorted(a_imports - b_imports)
    removed_imports = sorted(b_imports - a_imports)
    added_classes = sorted(a_classes - b_classes)
    removed_classes = sorted(b_classes - a_classes)

    # Detect structural changes
    structural_delta = {}
    for nt in ("loop", "try_block", "raise"):
        delta = a_types.get(nt, 0) - b_types.get(nt, 0)
        if delta != 0:
            structural_delta[nt] = delta

    # Verdict
    if not added_funcs and not removed_funcs and not structural_delta:
        verdict = "unchanged" if not added_imports and not removed_imports and not added_classes and not removed_classes else "minor"
    elif removed_funcs or removed_classes:
        verdict = "major"
    elif structural_delta:
        verdict = "structural"
    else:
        verdict = "minor"

    return {
        "added_functions": added_funcs,
        "removed_functions": removed_funcs,
        "added_imports": added_imports,
        "removed_imports": removed_imports,
        "added_classes": added_classes,
        "removed_classes": removed_classes,
        "structural_changes": structural_delta,
        "verdict": verdict,
        "before_node_count": before.get("node_count", 0),
        "after_node_count": after.get("node_count", 0),
    }


from collections import Counter


__all__ = [
    "parse_code_to_graph",
    "diff_graphs",
]
