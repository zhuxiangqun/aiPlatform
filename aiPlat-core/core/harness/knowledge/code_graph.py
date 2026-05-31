"""
Code Knowledge Graph — builds dependency graph from source imports.

Moved from aiPlat-core/core/api/routers/code_intel.py to comply with
CLAUDE.md §5.14 (harness must not import from api/routers).
"""

from __future__ import annotations

import ast
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
_CACHE_LOCK = None


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
    return [
        "aiPlat-core",
        "aiPlat-infra",
        "aiPlat-platform",
        "aiPlat-app",
        "aiPlat-management",
    ]


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


def _extract_py_imports_ast(filepath: Path) -> list:
    """Use Python's built-in AST to extract import module names.
    Replaces regex-based _PY_IMPORT_RE with 100% accurate parsing.
    Falls back to regex on SyntaxError."""
    try:
        text = _read_text(filepath)
        if not text:
            return []
        text = _strip_py_type_checking(text)
        tree = ast.parse(text, filename=str(filepath))
    except SyntaxError:
        # Fallback to regex for files with syntax issues
        mods = []
        for m in _PY_IMPORT_RE.finditer(text):
            mod = m.group(2) or m.group(3)
            if mod and not mod.startswith("TYPE_CHECKING"):
                mods.append(mod)
        return mods

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _extract_calls_ast(filepath: Path) -> list:
    """Extract function/method calls from a Python file using AST.
    Returns list of (function_name, line_number) tuples."""
    try:
        text = _read_text(filepath)
        if not text:
            return []
        text = _strip_py_type_checking(text)
        tree = ast.parse(text, filename=str(filepath))
    except SyntaxError:
        return []

    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Extract the function/method name from the call
            if isinstance(func, ast.Name):
                calls.append((func.id, func.lineno))
            elif isinstance(func, ast.Attribute):
                calls.append((func.attr, func.lineno))
    return calls


def _extract_symbols_ast(filepath: Path) -> list:
    """Extract function and class definitions from a Python file using AST.
    Returns list of (name, kind, line_number, parent_base) tuples where
    parent_base is the base class name for ClassDef, or None."""
    try:
        text = _read_text(filepath)
        if not text:
            return []
        text = _strip_py_type_checking(text)
        tree = ast.parse(text, filename=str(filepath))
    except SyntaxError:
        return []

    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols.append((node.name, "function", node.lineno, None))
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append((node.name, "async_function", node.lineno, None))
        elif isinstance(node, ast.ClassDef):
            parent = None
            if node.bases:
                first_base = node.bases[0]
                if isinstance(first_base, ast.Name):
                    parent = first_base.id
                elif isinstance(first_base, ast.Attribute):
                    parent = first_base.attr
            symbols.append((node.name, "class", node.lineno, parent))
    return symbols


_JS_FUNC_RE = re.compile(
    r'(?:export\s+)?(?:async\s+)?function\s+(\w+)'
    r'|(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\w+\s*=>|\([^)]*\)\s*=>|\()'
    r'|(?:export\s+)?class\s+(\w+)'
    r'|(?:export\s+)?(?:const|let|var)\s+(\w+)\s*:\s*(?:React\.)?(?:FC|FunctionComponent)',
    re.M | re.I
)


def _extract_js_symbols(filepath: Path) -> list:
    """Extract functions/classes from .ts/.tsx/.js/.jsx files via regex."""
    try:
        text = _read_text(filepath)
        if not text:
            return []
    except Exception:
        return []
    symbols = []
    for line_num, line in enumerate(text.split("\n"), 1):
        for m in _JS_FUNC_RE.finditer(line):
            for g in m.groups():
                if g and g not in ("const", "let", "var", "export", "default", "async"):
                    symbols.append([g, "function", line_num])
                    break
    return symbols


# ── JS/TS route & API call extraction ──────────────────────────

_ROUTE_PATH_RE = re.compile(r"""path\s*[:=]\s*['"]([^'"]+)['"]""", re.I)
_API_CALL_RE = re.compile(
    r"""(?:fetch|apiClient\.\w+|axios\.\w+|request\()\s*\(\s*['"`]((?:/api)?/core/\S*?)['"`]""",
    re.I
)
_BACKEND_ROUTE_RE = re.compile(r"""@router\.\w+\(\s*['"]([^'"]+)['"]""", re.I)


def _extract_js_routes(filepath: Path) -> list:
    """Extract React Router routes with component names from TSX/TS files.
    Returns list of [path, component_name, line_no, 'GET'] per route."""
    try:
        text = _read_text(filepath)
    except Exception:
        return []
    lines = text.split('\n')
    routes = []
    for i, line in enumerate(lines):
        for m in _ROUTE_PATH_RE.finditer(line):
            path = m.group(1)
            if not path or path.startswith('*'):
                continue
            # Try to find component/import in current line + next 3 lines
            scan = line + '\n' + '\n'.join(lines[i+1:i+4] if i+4 <= len(lines) else lines[i+1:])
            comp = ""
            # Pattern: element={withSuspense(Comp)} or element: withSuspense(Comp)
            ele_match = re.search(r'element\s*[:=]\s*\{?\s*withSuspense\((\w+)\)', scan)
            if ele_match:
                comp = ele_match.group(1)
            else:
                # Pattern: element={<Comp />}
                ele_match = re.search(r'element\s*[:=]\s*\{?\s*<(\w+)', scan)
                if ele_match:
                    comp = ele_match.group(1)
                else:
                    # Pattern: component={Comp}
                    comp_match = re.search(r'component\s*[:=]\s*\{?\s*(\w+)', scan)
                    if comp_match:
                        comp = comp_match.group(1)
            routes.append([path, comp, i + 1, 'GET'])
    return routes


def _extract_api_calls(filepath: Path) -> List[str]:
    """Extract backend API endpoint strings from frontend files."""
    try:
        text = _read_text(filepath)
    except Exception:
        return []
    endpoints = []
    for m in _API_CALL_RE.finditer(text):
        ep = m.group(1)
        if ep:
            # Normalize: remove /api and /core prefixes, query params
            ep = ep.replace('/api/', '/').replace('/core/', '/').split('?')[0].rstrip('/')
            endpoints.append(ep)
    return list(set(endpoints))


def _extract_backend_routes(filepath: Path) -> list:
    """Extract FastAPI @router routes with handler names and line numbers.
    Returns list of [path, handler_name, line_no, method] per route.
    Uses AST for Python files to reliably pair decorator→function.
    Falls back to regex for non-Python or syntax-error files."""
    ext = filepath.suffix.lower()
    if ext != ".py":
        # Fallback to regex for config files
        try:
            text = _read_text(filepath)
        except Exception:
            return []
        return [[m.group(1), "", 0, "GET"] for m in _BACKEND_ROUTE_RE.finditer(text) if m.group(1)]

    try:
        text = _read_text(filepath)
        if not text:
            return []
        tree = ast.parse(text, filename=str(filepath))
    except (SyntaxError, Exception):
        # Regex fallback
        result = []
        for m in _BACKEND_ROUTE_RE.finditer(text):
            path = m.group(1)
            if path:
                result.append([path, "", m.start() // max(1, text.count('\n', 0, m.start())), "GET"])
        return result

    routes = []
    methods = {"get", "post", "put", "delete", "patch", "head", "options"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                method, path = _parse_router_decorator(decorator, methods)
                if path:
                    routes.append([path, node.name, node.lineno, method.upper()])
    return routes


def _parse_router_decorator(decorator: ast.expr, methods: set) -> tuple:
    """Parse @router.get('/path') or @router.post('/path') decorator.
    Returns (method_str, path_str) or ("", "") if not a router decorator."""
    if not isinstance(decorator, ast.Call):
        return ("", "")
    # Check for @router.get, @router.post, etc.
    func = decorator.func
    method_name = ""
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name) and func.value.id == "router":
            method_name = func.attr
        elif isinstance(func.value, ast.Attribute) and _get_attr_name(func.value) == "router":
            method_name = func.attr
    if method_name not in methods:
        return ("", "")
    # Extract first string argument (the path)
    if decorator.args:
        first_arg = decorator.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            return (method_name, first_arg.value)
    return ("", "")


def _get_attr_name(node: ast.expr) -> str:
    """Get the full dotted name of an attribute chain."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _get_attr_name(node.value) + "." + node.attr
    return ""


def _link_frontend_to_backend(
    nodes: Dict[str, Any],
    edges: List[Dict[str, str]],
    frontend_files: List[Path],
    backend_files: List[Path],
    repo_root: Path,
):
    """Create cross-language edges: frontend API calls → backend routes."""
    route_index: Dict[str, str] = {}
    for bf in backend_files:
        if bf.suffix.lower() != ".py":
            continue
        for route in _extract_backend_routes(bf):
            # Handle both old str format and new [path, handler, line, method] format
            path = route[0] if isinstance(route, (list, tuple)) and len(route) > 0 else str(route)
            if path.startswith('/'):
                route_index.setdefault(path, str(bf.relative_to(repo_root)))

    for ff in frontend_files:
        rel_from = str(ff.relative_to(repo_root))
        api_calls = _extract_api_calls(ff)
        for ep in api_calls:
            if ep in route_index:
                rel_to = route_index[ep]
                if not any(e.get("from") == rel_from and e.get("to") == rel_to for e in edges):
                    edges.append({"from": rel_from, "to": rel_to, "kind": "api", "label": ep})
            else:
                for route, backend_file in route_index.items():
                    if _route_matches(ep, route):
                        if not any(e.get("from") == rel_from and e.get("to") == backend_file for e in edges):
                            edges.append({"from": rel_from, "to": backend_file, "kind": "api", "label": ep})
                        break


def _route_matches(api_path: str, route_pattern: str) -> bool:
    api_segs = api_path.strip('/').split('/')
    route_segs = route_pattern.strip('/').split('/')
    if len(api_segs) != len(route_segs):
        return False
    for a, r in zip(api_segs, route_segs):
        if r.startswith('{') and r.endswith('}'):
            continue  # FastAPI path parameter
        # Normalize JS template literal ${var} to match {var}
        if a.startswith('${') and a.endswith('}'):
            continue  # JS template parameter
        if a != r:
            return False
    return True


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
    # Cross-package fallback: when importing from a different monorepo package
    # (e.g., aiPlat-platform importing core.foo → check aiPlat-core/core/foo.py)
    for prefix in ("aiPlat-core", "aiPlat-infra", "aiPlat-platform",
                   "aiPlat-app", "aiPlat-management"):
        base = _repo_root / prefix
        cand1 = base / rel.with_suffix(".py")
        if cand1.exists(): return cand1
        cand2 = base / rel / "__init__.py"
        if cand2.exists(): return cand2
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
    global _CACHE, _CACHE_ROOTS, _CACHE_LOCK
    if _CACHE_LOCK is None:
        import threading as _th
        _CACHE_LOCK = _th.Lock()

    # Try SQLite persistence first — with incremental sync on stale files
    try:
        from core.harness.knowledge.code_graph_persist import has_cache, load_nodes, load_edges, init_db
        init_db()
        if has_cache():
            nodes = load_nodes()
            edges = load_edges()

            # Incremental sync: check mtime + content hash
            import time as _t, hashlib
            stale_files: List[Path] = []
            for nid, n in nodes.items():
                fpath = _repo_root / nid
                if not fpath.exists():
                    stale_files.append(fpath)
                    continue
                current_mtime = fpath.stat().st_mtime
                stored_mtime = n.get("_mtime", 0)
                if abs(current_mtime - stored_mtime) > 0.001:
                    # mtime changed → verify with content hash
                    try:
                        current_hash = hashlib.md5(fpath.read_bytes()[:65536]).hexdigest()
                    except Exception:
                        current_hash = ""
                    stored_hash = n.get("_hash", "")
                    if current_hash != stored_hash or not stored_hash:
                        stale_files.append(fpath)
                    else:
                        n["_mtime"] = current_mtime  # mtime-only change, content same

            # Incremental sync: only rescan changed files (up to 100)
            # Beyond 100 stale files → fall through to full disk rebuild
            if 0 < len(stale_files) <= 100:
                for f in stale_files:
                    rel = str(f.relative_to(_repo_root)) if f.exists() else ""
                    if rel in nodes:
                        del nodes[rel]
                    # Re-scan this file
                    if f.exists() and f.suffix.lower() == ".py":
                        if rel not in nodes:
                            nodes[rel] = {"id": rel, "path": rel, "ext": f.suffix.lower(),
                                          "out": [], "in": 0, "issue_count": 0, "symbols": []}
                        for mod in _extract_py_imports_ast(f):
                            tgt = _resolve_py_module(_repo_root, f, mod)
                            if tgt and tgt.exists():
                                rel_to = str(tgt.relative_to(_repo_root))
                                nodes.setdefault(rel_to, {"id": rel_to, "path": rel_to, "ext": tgt.suffix.lower(),
                                                "out": [], "in": 0, "issue_count": 0, "symbols": []})
                    try:
                        nodes[rel]["symbols"] = _extract_symbols_ast(f)
                    except Exception:
                        logging.getLogger("code_graph").debug("Symbol extraction failed", exc_info=True)
                    # Rebuild edges for stale file
                    edges = [e for e in edges if e["from"] != rel]
                    if f.exists():
                        text = _read_text(f)
                        deps = set()
                        for mod in _extract_py_imports_ast(f):
                            tgt = _resolve_py_module(_repo_root, f, mod)
                            if tgt and tgt.exists():
                                rel_to = str(tgt.relative_to(_repo_root))
                                deps.add(rel_to)
                        for d in sorted(deps):
                            edges.append({"from": rel, "to": d})
                            nodes[rel].setdefault("out", []).append(d)

                # Save incrementally updated graph
            try:
                from core.harness.knowledge.code_graph_persist import save_graph
                save_graph(nodes, edges, _repo_root)
            except Exception:
                logging.getLogger("code_graph").debug("Graph persistence skipped", exc_info=True)

                with _CACHE_LOCK:
                    _CACHE = {"nodes": nodes, "edges": edges, "issues": [], "_ts": _t.time()}
                    _CACHE_ROOTS = ";".join(str(r) for r in roots)
                return nodes, edges, []

            # 0 stale or >100 stale → if >100, force full disk rebuild below
            if len(stale_files) > 100:
                raise Exception("Too many stale files (>100), force full rebuild")
            else:
                # 0 stale: return loaded data with mtime updated
                for nid, n in nodes.items():
                    fpath = _repo_root / nid
                    if fpath.exists():
                        n["_mtime"] = fpath.stat().st_mtime
                # Rebuild cross-file call edges (not persisted in old cache)
                edges = [e for e in edges if e.get("kind", "import") != "calls"]
                loaded_files = [_repo_root / nid for nid in nodes if (_repo_root / nid).exists()]
                _resolve_cross_call_edges(nodes, edges, loaded_files, _repo_root)
                _link_frontend_to_backend(nodes, edges, loaded_files, loaded_files, _repo_root)
                with _CACHE_LOCK:
                    _CACHE = {"nodes": nodes, "edges": edges, "issues": [], "_ts": _t.time()}
                    _CACHE_ROOTS = ";".join(str(r) for r in roots)
                return nodes, edges, []
    except Exception:
        pass

    # Fallback: in-memory cache (120s TTL)
    roots_key = ";".join(str(r) for r in roots)
    import time as _t
    with _CACHE_LOCK:
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
        nodes[rel] = {"id": rel, "path": rel, "ext": f.suffix.lower(), "out": [], "in": 0, "issue_count": 0, "symbols": []}
    for f in files:
        rel_from = str(f.relative_to(_repo_root))
        text = _read_text(f)
        file_issues = _detect_issues(text)
        if file_issues:
            for it in file_issues: issues.append({**it, "file": rel_from})
            nodes[rel_from]["issue_count"] = len(file_issues)
        deps: Set[str] = set()
        if f.suffix.lower() == ".py":
            # AST-based extraction: imports + symbols + calls
            for mod in _extract_py_imports_ast(f):
                tgt = _resolve_py_module(_repo_root, f, mod)
                if tgt and tgt.exists():
                    rel_to = str(tgt.relative_to(_repo_root))
                    if rel_to in nodes and rel_to != rel_from: deps.add(rel_to)
            # Extract symbols (functions/classes)
            try:
                nodes[rel_from]["symbols"] = _extract_symbols_ast(f)
            except Exception:
                pass
        else:
            for m in _JS_IMPORT_RE.finditer(text):
                spec = m.group(1) or m.group(2) or m.group(3)
                if not spec: continue
                if spec.startswith("."):
                    tgt = _resolve_js_relative(f, spec)
                    if tgt and tgt.exists():
                        rel_to = str(tgt.relative_to(_repo_root))
                        if rel_to in nodes and rel_to != rel_from: deps.add(rel_to)
            # Extract TS/JS symbols (functions/classes via regex)
            if f.suffix.lower() in (".ts", ".tsx", ".js", ".jsx"):
                try:
                    nodes[rel_from]["symbols"] = _extract_js_symbols(f)
                    # Also extract route paths as metadata
                    routes = _extract_js_routes(f)
                    if routes:
                        nodes[rel_from]["routes"] = routes
                except Exception:
                    pass
        for rel_to in sorted(deps):
            edges.append({"from": rel_from, "to": rel_to})
            nodes[rel_from]["out"].append(rel_to)
            nodes[rel_to]["in"] += 1
        # Extract call edges (function→function calls within and across files)
        if f.suffix.lower() == ".py":
            try:
                calls = _extract_calls_ast(f)
                for func_name, line_no in calls[:50]:
                    edges.append({"from": rel_from, "to": rel_from, "kind": "calls",
                                  "label": f"{func_name}()", "line": line_no})
            except Exception:
                pass
    # Resolve cross-file call edges
    _resolve_cross_call_edges(nodes, edges, files, _repo_root)
    # Build cross-language edges: frontend API calls → backend routes
    _link_frontend_to_backend(nodes, edges, files, files, _repo_root)
    # Save to in-memory cache + SQLite persistence
    with _CACHE_LOCK:
        _CACHE = {"nodes": nodes, "edges": edges, "issues": issues, "_ts": _t.time()}
        _CACHE_ROOTS = roots_key
    try:
        from core.harness.knowledge.code_graph_persist import save_graph
        save_graph(nodes, edges, _repo_root)
    except Exception:
        pass
    return nodes, edges, issues


def clear_cache():
    u"""Invalidate in-memory cache only. SQLite data persists for incremental rebuild.
    Called by hot-reload on file change — next build_graph() only rescans changed files."""
    global _CACHE, _CACHE_ROOTS, _CACHE_LOCK
    if _CACHE_LOCK:
        with _CACHE_LOCK:
            _CACHE = None
            _CACHE_ROOTS = None
    else:
        _CACHE = None
        _CACHE_ROOTS = None


def build_symbol_graph(
    _repo_root: Path = None, roots: List[Path] = None
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Build a symbol-level code graph (each function/class is a node).

    Convenience wrapper that calls build_graph() then converts to symbol-level.
    Returns (symbol_nodes, symbol_edges).
    """
    if _repo_root is None:
        _repo_root = repo_root()
    if roots is None:
        roots = [(_repo_root / r).resolve() for r in default_roots()]
    file_nodes, file_edges, _ = build_graph(_repo_root, roots)
    return _build_symbol_graph(file_nodes, file_edges, _repo_root)


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


def _ctx_to_prompt(ctx: dict, max_chars: int = 2000) -> str:
    u"""Convert build_context() dict result to LLM-friendly clean text (no dict repr)."""
    lines = []
    stats = ctx.get("stats", {})
    lines.append(f"Codebase: {stats.get('files', 0)} files, {stats.get('edges', 0)} edges")
    health = ctx.get("health", {})
    if health:
        lines.append(f"Health: score={health.get('score', 'N/A')}, issues={stats.get('issues', 0)}")
    related = ctx.get("related", [])
    if related:
        lines.append("Relevant files:")
        for r in related:
            lines.append(f"  - {r.get('file', '')}")
    orphans = ctx.get("orphan_files", [])
    if orphans:
        lines.append(f"Orphans: {len(orphans)} isolated files")
    text = "\n".join(lines)
    return text[:max_chars]


def _enrich_nodes_with_symbols(nodes, repo_root):
    u"""Add entity-level symbol counts and top symbols to file nodes.

    NOTE: modifies nodes dict in-place (intentional — enrichment is idempotent
    and operates on cached graph nodes for performance).
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
    """Find files with no imports and no importers."""
    orphans = []
    for path, node in nodes.items():
        if not node.get("out") and node.get("in", 0) == 0:
            orphans.append(path)
    return orphans


def _layer_bucket(path: str) -> str:
    """Infer architecture layer from file path."""
    if not path:
        return "unknown"
    if any(x in path for x in ["infra/", "model/", "storage/"]):
        return "infra"
    if any(x in path for x in ["harness/", "syscall", "engine", "execution/"]):
        return "core"
    if any(x in path for x in ["api/rest/", "platform/", "gateway"]):
        return "platform"
    if any(x in path for x in ["frontend/", "src/pages", "src/components", "App.tsx"]):
        return "app"
    return "core"


def _build_symbol_graph(
    file_nodes: Dict[str, Any],
    file_edges: List[Dict[str, str]],
    repo_root: Path,
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Convert file-level graph to symbol-level graph.

    Each function/class becomes its own node.
    Intra-file call edges connect symbols within the same file.
    Import edges are expanded: if file A imports file B, all symbols in A
    that reference symbols in B get edges.
    """
    from collections import defaultdict

    symbol_nodes: Dict[str, Any] = {}
    symbol_edges: List[Dict[str, str]] = []

    # Index: function/class name → list of (file, symbol_info)
    name_index: Dict[str, List[Tuple[str, list]]] = defaultdict(list)

    # Phase 1: Create symbol nodes
    for file_id, fn in file_nodes.items():
        symbols = fn.get("symbols", [])
        routes = fn.get("routes", [])
        ext = fn.get("ext", "")
        layer = _layer_bucket(file_id)
        file_issues = fn.get("issue_count", 0)

        for sym in symbols:
            if not isinstance(sym, (list, tuple)) or len(sym) < 2:
                continue
            name = sym[0]
            kind = sym[1]
            line = sym[2] if len(sym) > 2 else 0

            symbol_id = f"{file_id}::{name}"
            symbol_nodes[symbol_id] = {
                "id": symbol_id,
                "name": name,
                "kind": kind,  # function | async_function | class
                "file": file_id,
                "line": line,
                "layer": layer,
                "ext": ext,
                "issue_count": 0,
            }
            name_index[name].append((file_id, sym))

    # Phase 2: Build intra-file call edges
    for file_id in file_nodes:
        # Re-extract calls and match to local symbols
        fpath = repo_root / file_id
        if not fpath.exists() or fpath.suffix.lower() != ".py":
            continue
        try:
            calls = _extract_calls_ast(fpath)
            local_symbols = {s[0] for s in file_nodes[file_id].get("symbols", [])}
            for func_name, line_no in calls:
                # Only create edge if the called function is a known symbol in this file
                if func_name in local_symbols:
                    caller_candidates = [
                        s for s in file_nodes[file_id].get("symbols", [])
                        if isinstance(s, (list, tuple)) and len(s) > 2 and s[2] < line_no
                    ]
                    caller_name = caller_candidates[-1][0] if caller_candidates else file_id
                    caller_id = f"{file_id}::{caller_name}"
                    callee_id = f"{file_id}::{func_name}"
                    if caller_id != callee_id:
                        symbol_edges.append({
                            "from": caller_id,
                            "to": callee_id,
                            "kind": "calls",
                            "label": f"{func_name}()",
                            "line": line_no,
                        })

            # Also scan for cross-file references through name_index
            for func_name, line_no in calls:
                if func_name not in local_symbols:
                    target_files = name_index.get(func_name, [])
                    for tf, _ in target_files[:2]:
                        if tf != file_id and tf in file_nodes:
                            caller_id = f"{file_id}::{file_id}"
                            callee_id = f"{tf}::{func_name}"
                            if callee_id in symbol_nodes:
                                symbol_edges.append({
                                    "from": caller_id,
                                    "to": callee_id,
                                    "kind": "cross_call",
                                    "label": f"{func_name}()",
                                    "line": line_no,
                                })
        except Exception:
            pass

    # Phase 3: Build import-based edges between symbols
    for edge in file_edges:
        if edge.get("from", "") in file_nodes and edge.get("to", "") in file_nodes:
            from_file = edge["from"]
            to_file = edge["to"]
            from_symbols = file_nodes[from_file].get("symbols", [])
            to_symbols = file_nodes[to_file].get("symbols", [])

            # Only create import edge if the file has symbols
            count = 0
            for fs in from_symbols[:3]:
                if not isinstance(fs, (list, tuple)) or len(fs) < 2:
                    continue
                from_id = f"{from_file}::{fs[0]}"
                for ts in to_symbols[:1]:
                    if not isinstance(ts, (list, tuple)) or len(ts) < 2:
                        continue
                    to_id = f"{to_file}::{ts[0]}"
                    if from_id != to_id:
                        symbol_edges.append({
                            "from": from_id,
                            "to": to_id,
                            "kind": "import",
                        })
                        count += 1
                if count >= 3:
                    break

    # Phase 4: Inherit routes to symbol nodes
    for file_id, fn in file_nodes.items():
        routes = fn.get("routes", [])
        if routes:
            for road in routes:
                # Handle both old format (str) and new format (list)
                if isinstance(road, str):
                    path, handler, line, method = road, "", 0, "GET"
                elif isinstance(road, (list, tuple)):
                    path = road[0] if len(road) > 0 else ""
                    handler = road[1] if len(road) > 1 else ""
                    line = road[2] if len(road) > 2 else 0
                    method = road[3] if len(road) > 3 else "GET"
                else:
                    continue
                label = f"{method} /{path}"
                route_node_id = f"{file_id}::route::{path}"
                symbol_nodes[route_node_id] = {
                    "id": route_node_id,
                    "name": label,
                    "kind": "route",
                    "file": file_id,
                    "line": line,
                    "layer": _layer_bucket(file_id),
                    "ext": fn.get("ext", ""),
                    "issue_count": 0,
                }
                # Link route to the handler function in this file
                for sym in fn.get("symbols", []):
                    if isinstance(sym, (list, tuple)) and len(sym) >= 2 and handler and sym[0] == handler:
                        symbol_edges.append({
                            "from": route_node_id,
                            "to": f"{file_id}::{sym[0]}",
                            "kind": "route_to",
                            "label": method,
                        })
                        break
                else:
                    # Fallback: link to first function
                    first_sym = fn.get("symbols", [])
                    if first_sym:
                        sym = first_sym[0]
                        if isinstance(sym, (list, tuple)) and len(sym) >= 2:
                            symbol_edges.append({
                                "from": route_node_id,
                                "to": f"{file_id}::{sym[0]}",
                                "kind": "route_to",
                                "label": path,
                            })

    return symbol_nodes, symbol_edges


def _build_inheritance_edges(
    nodes: Dict[str, Any], edges: List[Dict[str, str]]
) -> int:
    """Build inheritance edges from class parent info.

    Uses the parent field in symbols (4th element) to create is-a edges.
    Cross-references across files using the global symbol name index.
    Returns the number of inheritance edges created.
    """
    from collections import defaultdict

    # Index: class name → list of (file_id, symbol)
    name_index: Dict[str, List[Tuple[str, list]]] = defaultdict(list)
    for nid, nd in nodes.items():
        for sym in nd.get("symbols", []):
            if isinstance(sym, (list, tuple)) and len(sym) >= 2 and sym[1] == "class":
                name_index[sym[0]].append((nid, sym))

    added = 0
    for nid, nd in nodes.items():
        for sym in nd.get("symbols", []):
            if not isinstance(sym, (list, tuple)) or len(sym) < 4:
                continue
            parent = sym[3]  # 4th element = parent class name
            if not parent:
                continue
            # Find parent class in the same file or across files
            for child_file, child_sym in name_index.get(sym[0], []):
                for parent_file, parent_sym in name_index.get(parent, []):
                    if child_file in nodes and parent_file in nodes:
                        edges.append({
                            "from": child_file,
                            "to": parent_file,
                            "kind": "inherits",
                            "label": f"{sym[0]} → {parent}",
                        })
                        added += 1
    return added


def _resolve_cross_call_edges(nodes, edges, files, repo_root):
    u"""Rebuild cross-file call edges (kind='calls', cross=True).
    Removes stale calls-kind edges and regenerates from current graph state.
    """
    from collections import defaultdict
    fn_to_files = defaultdict(list)
    for nid, n in nodes.items():
        for sym in n.get("symbols", []):
            if not isinstance(sym, (list, tuple)) or len(sym) < 2:
                continue
            name = sym[0]
            kind = sym[1]
            if kind in ("function", "async_function", "class"):
                fn_to_files[name].append(nid)
    if not fn_to_files:
        return
    for f in files:
        if f.suffix.lower() != ".py":
            continue
        rel_from = str(f.relative_to(repo_root))
        try:
            calls = _extract_calls_ast(f)
            for func_name, line_no in calls[:30]:
                target_files = fn_to_files.get(func_name, [])
                for tf in target_files[:3]:
                    if tf != rel_from and tf in nodes:
                        edges.append({"from": rel_from, "to": tf, "kind": "calls",
                                      "label": f"{func_name}()", "line": line_no,
                                      "cross": True})
        except Exception:
            pass
