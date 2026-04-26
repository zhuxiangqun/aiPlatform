from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request

from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()


@dataclass
class _ScanResult:
    created_at: float
    roots_key: str
    stats: Dict[str, Any]
    nodes: Dict[str, Dict[str, Any]]  # path -> node
    edges: List[Dict[str, str]]  # {from,to}
    issues: List[Dict[str, Any]]


_CACHE: Optional[_ScanResult] = None
_CACHE_TTL_SEC = 120.0


def _repo_root() -> Path:
    """
    Try to locate monorepo root so we can scan:
      - aiPlat-core
      - aiPlat-management/frontend
    """
    here = Path(__file__).resolve()
    p = here
    for _ in range(12):
        if (p / "aiPlat-core").exists() and (p / "aiPlat-management").exists():
            return p
        p = p.parent
    # fallback: parent of aiPlat-core if present
    for _ in range(12):
        if p.name == "aiPlat-core":
            return p.parent
        p = p.parent
    return Path.cwd()


def _default_roots() -> List[str]:
    return ["aiPlat-core", "aiPlat-management/frontend"]


_PY_IMPORT_RE = re.compile(r"^\s*(from\s+([a-zA-Z0-9_\.]+)\s+import|import\s+([a-zA-Z0-9_\.]+))", re.M)
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+[^;]*?\s+from\s+['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
)


def _is_code_file(p: Path) -> bool:
    if not p.is_file():
        return False
    if p.name.startswith("."):
        return False
    ext = p.suffix.lower()
    return ext in {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".java", ".go", ".rs", ".rb", ".php"}


def _should_skip(p: Path) -> bool:
    parts = set(p.parts)
    if any(x in parts for x in {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", "dist", "build"}):
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
    candidates = []
    if base.suffix:
        candidates.append(base)
    else:
        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            candidates.append(Path(str(base) + ext))
        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            candidates.append(base / ("index" + ext))
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _resolve_py_module(repo_root: Path, from_file: Path, mod: str) -> Optional[Path]:
    # very lightweight resolver: map a.b.c to repo_root/**/a/b/c.py or a/b/c/__init__.py
    # We first try relative to repo root.
    rel = Path(*mod.split("."))
    cand1 = repo_root / rel.with_suffix(".py")
    cand2 = repo_root / rel / "__init__.py"
    if cand1.exists():
        return cand1
    if cand2.exists():
        return cand2
    # fallback: try relative to current package folder (walk up until found "core" etc.)
    pkg_root = from_file.parent
    for _ in range(6):
        cand = pkg_root / rel.with_suffix(".py")
        if cand.exists():
            return cand
        cand = pkg_root / rel / "__init__.py"
        if cand.exists():
            return cand
        pkg_root = pkg_root.parent
    return None


def _detect_issues(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not text:
        return out
    # Secrets (heuristics)
    if re.search(r"AKIA[0-9A-Z]{16}", text):
        out.append({"type": "secret", "severity": "high", "rule": "aws_access_key_id"})
    if re.search(r"-----BEGIN (?:RSA|EC|OPENSSH) PRIVATE KEY-----", text):
        out.append({"type": "secret", "severity": "high", "rule": "private_key_block"})
    if re.search(r"(api[_-]?key|secret|token)\s*=\s*['\"][^'\"]{12,}['\"]", text, re.I):
        out.append({"type": "secret", "severity": "medium", "rule": "hardcoded_token_like"})
    # Dangerous eval
    if re.search(r"\beval\s*\(", text):
        out.append({"type": "security", "severity": "medium", "rule": "eval_usage"})
    if re.search(r"\bexec\s*\(", text):
        out.append({"type": "security", "severity": "medium", "rule": "exec_usage"})
    return out


def _build_graph(repo_root: Path, roots: List[Path]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]], List[Dict[str, Any]]]:
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, str]] = []
    issues: List[Dict[str, Any]] = []

    # Collect files
    files: List[Path] = []
    for r in roots:
        if not r.exists():
            continue
        for p in r.rglob("*"):
            if _should_skip(p):
                continue
            if _is_code_file(p):
                files.append(p)

    # Index by path for quick lookup
    for f in files:
        rel = str(f.relative_to(repo_root))
        nodes[rel] = {"id": rel, "path": rel, "ext": f.suffix.lower(), "out": [], "in": 0, "issue_count": 0}

    # Parse imports
    for f in files:
        rel_from = str(f.relative_to(repo_root))
        text = _read_text(f)
        file_issues = _detect_issues(text)
        if file_issues:
            for it in file_issues:
                issues.append({**it, "file": rel_from})
            nodes[rel_from]["issue_count"] = len(file_issues)

        deps: Set[str] = set()
        if f.suffix.lower() == ".py":
            for m in _PY_IMPORT_RE.finditer(text):
                mod = m.group(2) or m.group(3)
                if not mod:
                    continue
                tgt = _resolve_py_module(repo_root, f, mod)
                if tgt and tgt.exists():
                    rel_to = str(tgt.relative_to(repo_root))
                    if rel_to in nodes and rel_to != rel_from:
                        deps.add(rel_to)
        else:
            for m in _JS_IMPORT_RE.finditer(text):
                spec = m.group(1) or m.group(2) or m.group(3)
                if not spec:
                    continue
                if spec.startswith("."):
                    tgt = _resolve_js_relative(f, spec)
                    if tgt and tgt.exists():
                        rel_to = str(tgt.relative_to(repo_root))
                        if rel_to in nodes and rel_to != rel_from:
                            deps.add(rel_to)

        for rel_to in sorted(deps):
            edges.append({"from": rel_from, "to": rel_to})
            nodes[rel_from]["out"].append(rel_to)
            nodes[rel_to]["in"] += 1

    return nodes, edges, issues


def _count_cycles(nodes: Dict[str, Dict[str, Any]]) -> int:
    # Simple cycle detection count (number of back-edges found in DFS).
    visiting: Set[str] = set()
    visited: Set[str] = set()
    back_edges = 0

    def dfs(u: str):
        nonlocal back_edges
        visiting.add(u)
        for v in nodes[u].get("out") or []:
            if v not in nodes:
                continue
            if v in visiting:
                back_edges += 1
            elif v not in visited:
                dfs(v)
        visiting.remove(u)
        visited.add(u)

    for u in list(nodes.keys()):
        if u not in visited:
            dfs(u)
    return back_edges


def _blast(nodes: Dict[str, Dict[str, Any]], start: str) -> List[str]:
    # forward reachability
    if start not in nodes:
        return []
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


async def _get_scan(rt, roots: List[str]) -> _ScanResult:
    global _CACHE
    roots_key = ",".join(roots)
    now = time.time()
    if _CACHE and _CACHE.roots_key == roots_key and (now - _CACHE.created_at) < _CACHE_TTL_SEC:
        return _CACHE

    repo_root = _repo_root()
    abs_roots = [(repo_root / r).resolve() for r in roots]
    nodes, edges, issues = _build_graph(repo_root, abs_roots)
    cycles = _count_cycles(nodes)
    stats = {
        "repo_root": str(repo_root),
        "roots": [str(r) for r in roots],
        "files": len(nodes),
        "edges": len(edges),
        "cycles_back_edges": cycles,
        "issues": len(issues),
    }
    _CACHE = _ScanResult(created_at=now, roots_key=roots_key, stats=stats, nodes=nodes, edges=edges, issues=issues)
    return _CACHE


@router.get("/diagnostics/code-intel/scan")
async def scan_code_intel(
    request: Request,
    roots: Optional[str] = None,
    rt=Depends(get_kernel_runtime),
):
    """
    Code intelligence scan (CodeFlow-inspired, server-side).
    Defaults to scanning: aiPlat-core + aiPlat-management/frontend
    """
    store = getattr(rt, "execution_store", None) if rt else None
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    root_list = [x.strip() for x in (roots.split(",") if roots else _default_roots()) if x.strip()]
    res = await _get_scan(rt, root_list)
    return {"status": "ok", "stats": res.stats, "nodes": list(res.nodes.values()), "edges": res.edges, "issues": res.issues}


@router.get("/diagnostics/code-intel/blast")
async def blast_radius(
    file: str,
    roots: Optional[str] = None,
    rt=Depends(get_kernel_runtime),
):
    root_list = [x.strip() for x in (roots.split(",") if roots else _default_roots()) if x.strip()]
    res = await _get_scan(rt, root_list)
    start = str(file).strip()
    out = _blast(res.nodes, start)
    return {"status": "ok", "file": start, "affected": out, "count": len(out)}

