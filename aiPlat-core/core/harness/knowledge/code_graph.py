"""
Code Knowledge Graph — builds dependency graph from source imports.

Moved from aiPlat-core/core/api/routers/code_intel.py to comply with
CLAUDE.md §5.14 (harness must not import from api/routers).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_PY_IMPORT_RE = re.compile(r"^\s*(from\s+([a-zA-Z0-9_\.]+)\s+import|import\s+([a-zA-Z0-9_\.]+))", re.M)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+[^;]*?\s+from\s+['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
)

# Module-level cache for build_graph results
_CACHE: Optional[Any] = None
_CACHE_ROOTS: Optional[str] = None


@dataclass
class ScanResult:
    created_at: float
    roots_key: str
    stats: Dict[str, Any]
    nodes: Dict[str, Dict[str, Any]]  # path -> node
    edges: List[Dict[str, str]]  # {from,to}
    issues: List[Dict[str, Any]]
    health: Dict[str, Any]


def repo_root() -> Path:
    here = Path(__file__).resolve()
    p = here
    for _ in range(12):
        if (p / "aiPlat-core").exists() and (p / "aiPlat-management").exists():
            return p
        p = p.parent
    for _ in range(12):
        if p.name == "aiPlat-core":
            return p.parent
        p = p.parent
    return Path.cwd()


def default_roots() -> List[str]:
    return ["aiPlat-core", "aiPlat-management/frontend"]


def _strip_py_type_checking(text: str) -> str:
    if "TYPE_CHECKING" not in text:
        return text
    lines = text.splitlines()
    out: List[str] = []
    skip = False
    skip_indent: Optional[int] = None
    for line in lines:
        if re.match(r"^\s*if\s+TYPE_CHECKING\s*:\s*$", line):
            skip = True
            skip_indent = None
            continue
        if skip:
            if skip_indent is None:
                if line.strip() == "":
                    continue
                skip_indent = len(line) - len(line.lstrip(" "))
            cur_indent = len(line) - len(line.lstrip(" "))
            if line.strip() != "" and skip_indent is not None and cur_indent < skip_indent:
                skip = False
                skip_indent = None
            else:
                continue
        if not skip:
            out.append(line)
    return "\n".join(out)


def _is_code_file(p: Path) -> bool:
    if not p.is_file() or p.name.startswith("."):
        return False
    ext = p.suffix.lower()
    return ext in {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".java", ".go", ".rs", ".rb", ".php"}


def _should_skip(p: Path) -> bool:
    parts = set(p.parts)
    if any(x in parts for x in {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
                                  ".ruff_cache", "node_modules", "dist", "build", "tests", "__tests__"}):
        return True
    if p.name.endswith((".min.js", ".map")):
        return True
    return False


def _read_text(p: Path, max_bytes: int = 800_000) -> str:
    try:
        if p.stat().st_size > max_bytes:
            return ""
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _resolve_js_relative(from_file: Path, spec: str) -> Optional[Path]:
    base = (from_file.parent / spec).resolve()
    candidates = [base] if base.suffix else []
    if not base.suffix:
        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            candidates.append(Path(str(base) + ext))
            candidates.append(base / ("index" + ext))
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _resolve_py_module(_repo_root: Path, from_file: Path, mod: str) -> Optional[Path]:
    u"""Resolve a Python import module to a file path.

    Handles: absolute (core.harness.X), relative (.Y, ..Z, .a.b)
    """
    if not mod:
        return None
    # Relative import: from . import X → mod = "."
    if mod == ".":
        # Resolve to from_file's parent package (__init__.py or directory)
        init = from_file.parent / "__init__.py"
        return init if init.exists() else None
    # Relative import: from .. import X or from .foo import bar
    if mod.startswith("."):
        num_dots = len(mod) - len(mod.lstrip("."))
        base_dir = from_file.parent
        for _ in range(num_dots - 1):
            base_dir = base_dir.parent
        mod = mod.lstrip(".")
        if not mod:
            init = base_dir / "__init__.py"
            return init if init.exists() else None
        rel = Path(*mod.split("."))
        cand1 = base_dir / rel.with_suffix(".py")
        if cand1.exists(): return cand1
        cand2 = base_dir / rel / "__init__.py"
        return cand2 if cand2.exists() else None
    # Absolute import
    rel = Path(*mod.split("."))
    cand1 = _repo_root / rel.with_suffix(".py")
    cand2 = _repo_root / rel / "__init__.py"
    if cand1.exists(): return cand1
    if cand2.exists(): return cand2
    pkg_root = from_file.parent
    for _ in range(6):
        cand = pkg_root / rel.with_suffix(".py")
        if cand.exists(): return cand
        cand = pkg_root / rel / "__init__.py"
        if cand.exists(): return cand
        pkg_root = pkg_root.parent
    return None


def _detect_issues(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not text: return out
    if re.search(r"AKIA[0-9A-Z]{16}", text):
        out.append({"type": "secret", "severity": "high", "rule": "aws_access_key_id"})
    if re.search(r"-----BEGIN (?:RSA|EC|OPENSSH) PRIVATE KEY-----", text):
        out.append({"type": "secret", "severity": "high", "rule": "private_key_block"})
    if re.search(r"(api[_-]?key|secret|token)\s*=\s*['\"][^'\"]{12,}['\"]", text, re.I):
        out.append({"type": "secret", "severity": "medium", "rule": "hardcoded_token_like"})
    if re.search(r"\beval\s*\(", text):
        out.append({"type": "security", "severity": "medium", "rule": "eval_usage"})
    if re.search(r"\bexec\s*\(", text):
        out.append({"type": "security", "severity": "medium", "rule": "exec_usage"})
    return out


def build_graph(_repo_root: Path, roots: List[Path]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]], List[Dict[str, Any]]]:
    global _CACHE, _CACHE_ROOTS
    roots_key = ";".join(str(r) for r in roots)
    # Use cache if roots match
    import time as _t
    if _CACHE and _CACHE_ROOTS == roots_key and _t.time() - _CACHE["_ts"] < 120:
        return _CACHE["nodes"], _CACHE["edges"], _CACHE["issues"]

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, str]] = []
    issues: List[Dict[str, Any]] = []
    files: List[Path] = []
    for r in roots:
        if not r.exists(): continue
        for p in r.rglob("*"):
            if _should_skip(p): continue
            if _is_code_file(p): files.append(p)
    for f in files:
        rel = str(f.relative_to(_repo_root))
        nodes[rel] = {"id": rel, "path": rel, "ext": f.suffix.lower(), "out": [], "in": 0, "issue_count": 0}
    for f in files:
        rel_from = str(f.relative_to(_repo_root))
        text = _read_text(f)
        file_issues = _detect_issues(text)
        if file_issues:
            for it in file_issues: issues.append({**it, "file": rel_from})
            nodes[rel_from]["issue_count"] = len(file_issues)
        deps: Set[str] = set()
        if f.suffix.lower() == ".py":
            text = _strip_py_type_checking(text)
            for m in _PY_IMPORT_RE.finditer(text):
                mod = m.group(2) or m.group(3)
                if not mod: continue
                tgt = _resolve_py_module(_repo_root, f, mod)
                if tgt and tgt.exists():
                    rel_to = str(tgt.relative_to(_repo_root))
                    if rel_to in nodes and rel_to != rel_from: deps.add(rel_to)
        else:
            for m in _JS_IMPORT_RE.finditer(text):
                spec = m.group(1) or m.group(2) or m.group(3)
                if not spec: continue
                if spec.startswith("."):
                    tgt = _resolve_js_relative(f, spec)
                    if tgt and tgt.exists():
                        rel_to = str(tgt.relative_to(_repo_root))
                        if rel_to in nodes and rel_to != rel_from: deps.add(rel_to)
        for rel_to in sorted(deps):
            edges.append({"from": rel_from, "to": rel_to})
            nodes[rel_from]["out"].append(rel_to)
            nodes[rel_to]["in"] += 1
    # Save to cache
    _CACHE = {"nodes": nodes, "edges": edges, "issues": issues, "_ts": _t.time()}
    _CACHE_ROOTS = roots_key
    return nodes, edges, issues


def clear_cache():
    u"""Invalidate the code graph cache (called by hot-reload on file changes)."""
    global _CACHE, _CACHE_ROOTS
    _CACHE = None
    _CACHE_ROOTS = None


def count_cycles(nodes: Dict[str, Dict[str, Any]]) -> int:
    visiting: Set[str] = set()
    visited: Set[str] = set()
    back_edges = 0
    def dfs(u: str):
        nonlocal back_edges
        visiting.add(u)
        for v in nodes[u].get("out") or []:
            if v not in nodes: continue
            if v in visiting: back_edges += 1
            elif v not in visited: dfs(v)
        visiting.remove(u)
        visited.add(u)
    for u in list(nodes.keys()):
        if u not in visited: dfs(u)
    return back_edges


def health_score(*, nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, str]],
                 issues: List[Dict[str, Any]], cycles_back_edges: int) -> Dict[str, Any]:
    files = max(1, len(nodes))
    e = len(edges)
    issue_count = len(issues)
    degs = []
    max_deg = 0
    for n in nodes.values():
        d = int((len(n.get("out") or [])) + int(n.get("in") or 0))
        degs.append(d)
        max_deg = max(max_deg, d)
    avg_deg = (sum(degs) / len(degs)) if degs else 0.0
    issue_density = issue_count / files
    score = 100.0
    score -= min(40.0, cycles_back_edges * 1.5)
    score -= min(25.0, issue_density * 80.0)
    score -= min(20.0, max(0.0, avg_deg - 3.0) * 2.0)
    score -= min(15.0, max(0.0, (e / files) - 1.2) * 6.0)
    score = max(0.0, min(100.0, score))
    grade = "A"
    if score < 90: grade = "B"
    if score < 75: grade = "C"
    if score < 60: grade = "D"
    if score < 45: grade = "F"
    return {"score": round(score, 1), "grade": grade,
            "signals": {"files": files, "edges": e, "cycles_back_edges": cycles_back_edges,
                        "issues": issue_count, "avg_degree": round(avg_deg, 2),
                        "max_degree": int(max_deg), "issue_density": round(issue_density, 4)}}


def blast(nodes: Dict[str, Dict[str, Any]], start: str) -> List[str]:
    if start not in nodes: return []
    q = [start]
    seen = {start}
    out: List[str] = []
    while q:
        u = q.pop(0)
        for v in nodes[u].get("out") or []:
            if v in nodes and v not in seen:
                seen.add(v)
                q.append(v)
                out.append(v)
    return out


def build_context(task: str, roots: List[str] = None) -> Dict[str, Any]:
    u"""Hybrid context builder: scan and return relevant code graph for a task."""
    _repo_root = repo_root()
    if roots is None:
        roots = default_roots()
    abs_roots = [(_repo_root / r).resolve() for r in roots]
    nodes, edges, issues = build_graph(_repo_root, abs_roots)
    # Enrich with entity-level symbols (functions/classes via AST)
    _enrich_nodes_with_symbols(nodes, _repo_root)
    cycles = count_cycles(nodes)
    health = health_score(nodes=nodes, edges=edges, issues=issues, cycles_back_edges=cycles)
    task_lower = task.lower()
    # Filter nodes matching task keywords
    matching = {p: n for p, n in nodes.items() if any(
        kw in p.lower() for kw in task_lower.split() if len(kw) > 2
    )}
    related_files = []
    for p in list(matching.keys())[:15]:
        related_files.append({"file": p, "imports": nodes[p].get("out", [])[:5]})
    return {
        "task": task,
        "stats": {"files": len(nodes), "edges": len(edges), "issues": len(issues)},
        "health": health,
        "related": related_files,
        "orphan_files": _find_orphans(nodes),
    }


def _enrich_nodes_with_symbols(nodes, repo_root):
    u"""Add entity-level symbol counts and top symbols to file nodes.

    Uses ast.parse (same approach as repo_map.py) for zero-dependency extraction.
    Only processes .py files; JS/TS files get basic type hints.
    """
    import ast
    for path, node in nodes.items():
        if not path.endswith(".py"):
            continue
        try:
            file_path = repo_root / path
            code = _read_text(file_path, max_bytes=200000)
            if not code:
                continue
            tree = ast.parse(code)
            classes = []
            functions = []
            for n in ast.walk(tree):
                if isinstance(n, ast.ClassDef):
                    classes.append(n.name)
                elif isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
                    functions.append(n.name)
            node["entities"] = {
                "classes": classes[:10],
                "functions": functions[:15],
                "total_classes": len(classes),
                "total_functions": len(functions),
            }
        except (SyntaxError, OSError):
            pass


def _find_orphans(nodes):
    u"""Find files with no imports and no dependents, excluding structural files."""
    orphans = []
    for p, n in nodes.items():
        if len(n.get("out", [])) != 0 or n.get("in", 0) != 0:
            continue
        name = str(p)
        # Skip package init and barrel exports
        if name.endswith("__init__.py") or name.endswith("index.ts") or name.endswith("index.tsx"):
            continue
        # Skip config files
        if ".config.js" in name or ".config.ts" in name:
            continue
        # Skip UI library files (re-exported through barrel)
        if "/components/ui/" in name or "/components/common/" in name:
            continue
        # Skip pages subdirectory barrel exports
        if "/pages/" in name and name.count("/") >= 3 and (name.endswith("/index.ts") or name.endswith("/index.tsx")):
            continue
        # Skip tailwind/postcss/eslint config
        for kw in ["tailwind.config", "postcss.config", "eslint.config", "vite.config", "proxy_server"]:
            if kw in name:
                continue
        orphans.append(name)
    return orphans
