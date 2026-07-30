#!/usr/bin/env python3
"""
Frontend Infrastructure Guard — §43 + §44 + §45 + §46

§43: Vite proxy routing — verifies proxy targets are correct
§44: Cross-language API contract — checks TS fetch fields vs Python endpoint params
§45: Cross-language API path contract — frontend paths must match backend routes
§46: Frontend import path hygiene — barrel file enforcement

Usage:
    python3 scripts/guard_frontend.py
Output: text (same format as architecture_guard.sh), exit code 0=pass, 1=violations.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent

# §45 path-mismatch baseline ratchet: existing contract breakages are tracked here;
# the guard fails only on NEW mismatches (signatures not in this baseline).
PATH_MISMATCH_BASELINE = Path(__file__).resolve().parent / "baselines" / "frontend_path_mismatch_baseline.txt"


def bold(s): return f"\033[1m{s}\033[0m"
def red(s): return f"\033[0;31m{s}\033[0m"
def green(s): return f"\033[0;32m{s}\033[0m"
def yellow(s): return f"\033[0;33m{s}\033[0m"


def _normalize_fe_template(path: str) -> str:
    """Normalize a frontend template-literal path to a comparable route path.

    Rules (handles `apiClient.get(`/a/${id}/b${qs ? '?'+qs : ''}`)` style):
      - A `${...}` preceded by '/' is a PATH PARAM     → `{param}`.
      - A `${...}` NOT preceded by '/' is a QUERY/SUFFIX builder
        (e.g. `${qs}`, `${qs ? '?'+qs : ''}`) → strip it and everything after.
        Also handles truncated suffixes from nested-backtick extraction
        (e.g. captured `/core/prompts${qs ? ` with no closing brace).
      - Strip any literal query string (`?...`).
    """
    # Strip the first suffix-style ${ (not preceded by '/') and everything after it,
    # whether or not it is closed (nested backtick templates truncate the closing brace).
    path = re.sub(r"(?<!/)\$\{.*$", "", path, count=1)
    # Remaining ${...} occurrences are path params.
    path = re.sub(r"\$\{[^{}]*\}", "{param}", path)
    # Strip literal query string.
    path = path.split("?")[0]
    return path


# ═══════════════════════════════════════════════════════════════
# §43: Vite Proxy Routing Check
# ═══════════════════════════════════════════════════════════════

def check_vite_proxy() -> list[dict]:
    """Verify vite.config.ts proxy targets point to correct ports."""
    issues = []
    vite_config = WORKSPACE_ROOT / "aiPlat-management" / "frontend" / "vite.config.ts"
    if not vite_config.exists():
        return [{"level": "warning", "msg": "vite.config.ts not found — skipping proxy check"}]

    content = vite_config.read_text(encoding="utf-8")

    # Extract proxy rules: pattern → target, port
    proxy_entries = re.findall(
        r"'([^']+)'\s*:\s*\{[^}]*?target:\s*'([^']+)'[^}]*\}",
        content, re.DOTALL
    )

    # Known server processes (port → expected module)
    expected = {
        "8000": "management.server:create_app",
        "8001": "infra.management.api.main:create_app",
        "8002": "server:app",
        "8003": "api.rest.routes:app",
        "8004": "api.rest.routes:app",
    }

    # Check running processes
    running_ports = _get_running_ports()

    violations = 0
    for pattern, target in proxy_entries:
        port_match = re.search(r':(\d+)$', target)
        if not port_match:
            continue
        port = port_match.group(1)

        # Check 1: Is the target port alive?
        if port not in running_ports:
            issues.append({
                "code": "proxy_dead_target",
                "level": "warning",
                "msg": f"proxy '{pattern}' → {target} — port {port} has no running process",
                "files": [str(vite_config.relative_to(WORKSPACE_ROOT))],
            })
            violations += 1

        # Check 2: /api/core catch-all must point to 8002 (has all core routes)
        if pattern == "/api/core" and port != "8002":
            issues.append({
                "code": "proxy_core_misdirected",
                "level": "error",
                "msg": f"/api/core catch-all proxy → port {port} (must be 8002 — core routes live there)",
                "files": [str(vite_config.relative_to(WORKSPACE_ROOT))],
            })
            violations += 1

        # Check 3: /api/core/workspace/* routes should NOT go to 8000 (management)
        if pattern.startswith("/api/core/workspace/") and port == "8000":
            issues.append({
                "code": "proxy_workspace_to_management",
                "level": "error",
                "msg": f"'{pattern}' → port 8000 (management) — workspace routes must go to 8002 (core)",
                "files": [str(vite_config.relative_to(WORKSPACE_ROOT))],
            })
            violations += 1

    if not issues and proxy_entries:
        issues.append({
            "code": "proxy_ok",
            "level": "pass",
            "msg": f"All {len(proxy_entries)} proxy rules verified",
        })

    return issues


def _get_running_ports() -> set[str]:
    """Get set of ports with running Python processes."""
    ports = set()
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split("\n"):
            if "uvicorn" not in line and "python" not in line:
                continue
            for m in re.finditer(r'--port\s+(\d+)', line):
                ports.add(m.group(1))
    except Exception:
        pass
    return ports


# ═══════════════════════════════════════════════════════════════
# §44: Cross-Language API Contract Check
# ═══════════════════════════════════════════════════════════════

def check_api_contract() -> list[dict]:
    """Check frontend fetch() body fields vs backend endpoint parameters."""
    issues = []

    # Known mismatches to scan for (pattern-driven, expandable)
    checks = [
        {
            "name": "MCP test-invoke args vs arguments",
            "ts_files": ["aiPlat-management/frontend/src/pages/Workspace/MCP/MCP.tsx"],
            "ts_pattern": r'body\.arguments\s*=\s*args|"arguments"\s*:',
            "py_files": ["aiPlat-core/core/api/routers/mcp_admin.py"],
            "py_pattern": r'"arguments"',
            "expect": "arguments",  # frontend sends "arguments", backend must accept it
            "section": "§44",
        },
        # Add more contract checks here as patterns emerge
    ]

    for check in checks:
        ts_found = False
        py_found = False
        py_key = None

        for ts_file in check["ts_files"]:
            fp = WORKSPACE_ROOT / ts_file
            if not fp.exists():
                continue
            if re.search(check["ts_pattern"], fp.read_text(encoding="utf-8")):
                ts_found = True
                break

        for py_file in check["py_files"]:
            fp = WORKSPACE_ROOT / py_file
            if not fp.exists():
                continue
            m = re.search(check["py_pattern"], fp.read_text(encoding="utf-8"))
            if m:
                py_found = True
                py_key = m.group(0)
                break

        if ts_found and py_found:
            if check["expect"] in str(py_key):
                issues.append({
                    "code": "contract_ok",
                    "level": "pass",
                    "msg": f"{check['name']}: frontend+backend field '{check['expect']}' consistent",
                })
            else:
                issues.append({
                    "code": "contract_mismatch",
                    "level": "error",
                    "msg": f"{check['name']}: field mismatch — backend uses '{py_key}'",
                    "files": [str(WORKSPACE_ROOT / f) for f in check["ts_files"]],
                })

    if not any(i.get("code") in ("contract_mismatch", "contract_ok") for i in issues):
        issues.append({
            "code": "contract_ok",
            "level": "pass",
            "msg": "No contract checks defined or all files missing — extend guard_frontend.py",
        })

    return issues


# ═══════════════════════════════════════════════════════════════
# §45: Cross-Language API Path Contract
# ═══════════════════════════════════════════════════════════════

def _resolve_api_helper(subpath: str, helpers: dict[str, str], preceding_content: str) -> str:
    """Resolve a fetch(API('...')) call to a full path using the API helper base prefix.
    
    If helpers dict is empty, try to find the API definition in the preceding content.
    """
    if helpers:
        # Use the first matching helper (usually just 'API')
        base = next(iter(helpers.values()), "")
        if base:
            return base + subpath
    
    # Fallback: try to find const API = ... in the preceding file content
    m = re.search(r"const\s+API\s*=\s*\([^)]*\)\s*(?::\s*\w+)?\s*=>\s*(['\"`])((?:/[^'\"`$\n]{3,}))\2", preceding_content)
    if m:
        return m.group(2).rstrip("/") + subpath
    return ""


def _extract_frontend_paths() -> list[dict]:
    entries = []
    frontend_dirs = [
        WORKSPACE_ROOT / "aiPlat-management" / "frontend" / "src",
        WORKSPACE_ROOT / "aiPlat-app" / "src",
    ]
    for frontend_src in frontend_dirs:
        if not frontend_src.exists():
            continue
        entries.extend(_extract_frontend_paths_from_dir(str(frontend_src)))
    return entries


def _extract_frontend_paths_from_dir(frontend_dir: str) -> list[dict]:
    entries = []

    api_patterns = [
        # apiClient.get<T>('path', ...) — optional generic type arg; 2 groups: (method, path)
        (re.compile(r"apiClient\s*\.\s*(get|post|put|delete|patch)\s*(?:<[^>]*>)?\s*\(\s*['\"]([^'\"]+)['\"]"), "apiClient"),
        # apiClient.get<T>(`path`, ...) — optional generic type arg; 2 groups: (method, path)
        (re.compile(r"apiClient\s*\.\s*(get|post|put|delete|patch)\s*(?:<[^>]*>)?\s*\(\s*`([^`]+)`"), "apiClient"),
        # fetch('/path', ...) — 1 group: (path), check context for {method: 'POST'}
        (re.compile(r"fetch\s*\(\s*['\"]((?:/[^'\"]+))['\"]"), "fetch"),
        # fetch(API('subpath'), ...) — via API helper function; 1 group: subpath
        (re.compile(r"fetch\s*\(\s*API\s*\(\s*['\"]((?:/[^'\"]*)?)['\"]\s*\)"), "fetch_api"),
        # fetch(API(`subpath`), ...) — via API helper with template literal; 1 group: subpath
        (re.compile(r"fetch\s*\(\s*API\s*\(\s*`([^`]*)`\s*\)"), "fetch_api"),
    ]

    for root, dirs, files in os.walk(frontend_dir):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".git")]
        for fn in files:
            if not fn.endswith((".ts", ".tsx")):
                continue
            fp = os.path.join(root, fn)
            try:
                content = open(fp, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue

            # ── Extract API helper base paths (e.g. const API = (path) => '/prefix' + path) ──
            api_helpers: dict[str, str] = {}
            for hm in re.finditer(
                r"const\s+(\w+)\s*=\s*\([^)]*\)\s*(?::\s*\w+)?\s*=>\s*(['\"`])((?:/[^'\"`$\n]{3,}))\2",
                content,
            ):
                helper_name, _, base_path = hm.group(1), hm.group(2), hm.group(3)
                api_helpers[helper_name] = base_path.rstrip("/")

            for pattern, pat_type in api_patterns:
                for m in pattern.finditer(content):
                    if pat_type == "apiClient":
                        method, path = m.group(1).upper(), m.group(2)
                        # apiClient has baseUrl=/api, prepend it
                        if not path.startswith("/api"):
                            path = "/api" + path
                    elif pat_type == "fetch_api":
                        # fetch(API('/subpath')) — resolve via API helper
                        subpath = m.group(1)
                        full_path = _resolve_api_helper(subpath, api_helpers, content[:m.start()])
                        if not full_path:
                            continue
                        path = full_path
                        method = "GET"
                        # check for method override in fetch options
                        end_pos = m.end()
                        tail = content[end_pos:end_pos + 200]
                        method_match = re.search(r"method\s*:\s*['\"]([^'\"]+)['\"]", tail)
                        if method_match:
                            method = method_match.group(1).upper()
                    else:
                        # fetch() — try to detect method from options
                        path = m.group(1)
                        end_pos = m.end()
                        # Search up to 200 chars after the function call for {method: 'POST'}
                        tail = content[end_pos:end_pos + 200]
                        method_match = re.search(r"method\s*:\s*['\"]([^'\"]+)['\"]", tail)
                        method = method_match.group(1).upper() if method_match else "GET"
                    if not path.startswith("/") or "//" in path:
                        continue
                    normalized = _normalize_fe_template(path)
                    entries.append({
                        "method": method,
                        "path": normalized,
                        "file": os.path.relpath(fp, str(WORKSPACE_ROOT)),
                        "line": content[:m.start()].count("\n") + 1,
                    })
    return entries


def _build_mount_prefixes() -> dict[str, str]:
    """Build a mapping: router_file_basename → effective mount prefix.
    
    Scans server.py files for:
      api_router = APIRouter(prefix="/api/core")
      api_router.include_router(x_router)
      from ... import router as x_router
    """
    prefix_map: dict[str, str] = {}
    server_files = list(WORKSPACE_ROOT.glob("aiPlat-core/core/server.py"))
    server_files += list(WORKSPACE_ROOT.glob("aiPlat-platform/*/server.py"))
    server_files += list(WORKSPACE_ROOT.glob("aiPlat-platform/*/routes.py"))
    server_files += list(WORKSPACE_ROOT.glob("aiPlat-platform/api/rest/routes.py"))

    for sf in server_files:
        if not sf.exists():
            continue
        try:
            content = sf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Extract router definitions: xyz_router = APIRouter(prefix="...")
        router_prefixes: dict[str, str] = {}
        for m in re.finditer(r"(\w+)\s*=\s*APIRouter\s*\(\s*prefix\s*=\s*['\"]([^'\"]+)['\"]", content):
            var_name, prefix = m.group(1), m.group(2)
            router_prefixes[var_name] = prefix

        # Extract include_router calls and map to import aliases
        # Pattern: router_name.include_router(alias) or router_name.include_router(alias, prefix=...)
        for m in re.finditer(r"(\w+)\.include_router\s*\(\s*(\w+)\s*(?:,\s*prefix\s*=\s*['\"]([^'\"]+)['\"])?\s*\)", content):
            parent_var, child_var, extra_prefix = m.group(1), m.group(2), m.group(3)
            effective_prefix = router_prefixes.get(parent_var, "")
            if extra_prefix:
                effective_prefix = effective_prefix + extra_prefix

            if not effective_prefix:
                continue

            # Find the import: from path import router as child_var
            import_name = ""
            for im in re.finditer(
                rf"(?:from\s+(\S+)\s+import\s+router\s+as\s+{re.escape(child_var)}\b"
                rf"|from\s+(\S+)\s+import\s+.*\b{re.escape(child_var)}\b"
                rf"|import\s+(\S+)\s+as\s+{re.escape(child_var)}\b)",
                content):
                mod = im.group(1) or im.group(2) or im.group(3) or ""
                if mod:
                    import_name = mod.replace(".", "/") + ".py"
                    break

            if import_name:
                basename = os.path.basename(import_name)
                if basename not in prefix_map:
                    prefix_map[basename] = effective_prefix
                # Also try the full module path
                prefix_map[import_name] = effective_prefix
        
        # ── Auto-discovery detection: pkgutil.iter_modules pattern ──
        # server.py uses dynamic import for all routers under core/api/routers/:
        #   api_router = APIRouter(prefix="/api/core")
        #   pkgutil.iter_modules(_routers_pkg_path)
        #   api_router.include_router(_router)
        # This pattern is not regex-detectable by the explicit import scan above.
        if re.search(r'pkgutil\.iter_modules.*routers', content):
            # Find the effective prefix for this api_router
            auto_prefix = ""
            for var, prefix in router_prefixes.items():
                # api_router and _api are the two common patterns
                if 'api' in var.lower() and 'prefix' not in var.lower():
                    auto_prefix = prefix
                    break
            if not auto_prefix:
                auto_prefix = "/api/core"  # default for core server
            
            # Enumerate all router files
            routers_dir = WORKSPACE_ROOT / "aiPlat-core" / "core" / "api" / "routers"
            if routers_dir.is_dir():
                for rf in routers_dir.glob("*.py"):
                    prefix_map[rf.name] = auto_prefix
    return prefix_map


def _propagate_platform_app_prefixes(prefix_map: dict[str, str]):
    """Propagate mount prefixes through nested include_router chains in platform apps.
    
    For example, routes.py mounts router.py at /api/platform/apps, and router.py
    includes fde.py (which has its own prefix /fde). This function ensures that
    fde.py is registered with the full mount prefix /api/platform/apps.
    """
    apps_api_dir = WORKSPACE_ROOT / "aiPlat-platform" / "apps"
    if not apps_api_dir.is_dir():
        return

    # Build a reverse map: filename → list of (parent_filename, parent_path)
    include_graph: dict[str, list[tuple[str, Path]]] = {}
    for app_dir in apps_api_dir.iterdir():
        if not app_dir.is_dir() or app_dir.name.startswith("_"):
            continue
        api_dir = app_dir / "api"
        if not api_dir.is_dir():
            continue
        for py_file in api_dir.glob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            # Find from .xxx import router as _yyy_router
            imports: dict[str, str] = {}
            for m in re.finditer(
                r"from\s+\.(\S+)\s+import\s+router\s+as\s+(\w+)",
                content,
            ):
                mod_name, alias = m.group(1), m.group(2)
                imports[alias] = f"{mod_name}.py"

            # Find router.include_router(_yyy_router [, ...])
            for m in re.finditer(r"router\.include_router\s*\(\s*(\w+)", content):
                child_alias = m.group(1)
                if child_alias in imports:
                    child_file = imports[child_alias]
                    include_graph.setdefault(child_file, []).append((py_file.name, py_file))

    # Propagate prefixes: if router.py has prefix X and includes fde.py, fde.py gets X + router_self_prefix
    # Do multiple passes until stable (handles deeper chains)
    changed = True
    while changed:
        changed = False
        for child_file, parent_entries in include_graph.items():
            if child_file in prefix_map:
                continue
            for parent_file, parent_path in parent_entries:
                parent_prefix = prefix_map.get(parent_file, "")
                if parent_prefix:
                    # Also find the parent router's self-prefix (e.g., router.py has APIRouter(prefix="/ontology-editor"))
                    parent_self_prefix = ""
                    try:
                        parent_content = parent_path.read_text(encoding="utf-8", errors="ignore")
                        m = re.search(r"APIRouter\s*\(\s*prefix\s*=\s*['\"]([^'\"]+)['\"]", parent_content[:5000])
                        if m:
                            parent_self_prefix = m.group(1)
                    except Exception:
                        pass
                    prefix_map[child_file] = parent_prefix + parent_self_prefix
                    changed = True
                    break


def _extract_backend_routes() -> list[dict]:
    entries = []
    mount_prefixes = _build_mount_prefixes()
    _propagate_platform_app_prefixes(mount_prefixes)
    backend_dirs = [
        WORKSPACE_ROOT / "aiPlat-platform",
        WORKSPACE_ROOT / "aiPlat-core",
        WORKSPACE_ROOT / "aiPlat-infra",
        WORKSPACE_ROOT / "aiPlat-app",
        WORKSPACE_ROOT / "aiPlat-management",
    ]
    route_patterns = [
        # Standard decorator: @router.get("/path"), @app.post("/path")
        (re.compile(r"@(?:api_router|router|app)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]*)['\"]"), "method"),
        # Flask-style: @app.route("/path")
        (re.compile(r"@(?:app|router)\s*\.\s*route\s*\(\s*['\"]([^'\"]+)['\"]"), "flask_route"),
        # Dynamic registration: router.route("path", method, ...)
        (re.compile(r"(?:api_router|router|app)\s*\.\s*route\s*\(\s*['\"]([^'\"]+)['\"]"), "dynamic_route"),
        # add_api_route: router.add_api_route("/path", handler, methods=["GET"])
        (re.compile(r"(?:api_router|router|app)\s*\.\s*add_api_route\s*\(\s*['\"]([^'\"]+)['\"]"), "api_route"),
    ]
    for base_dir in backend_dirs:
        if not base_dir.exists():
            continue
        for root, dirs, files in os.walk(str(base_dir)):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules", "venv", ".venv")]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                fp = os.path.join(root, fn)
                try:
                    content = open(fp, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                # Determine mount prefix for this file
                mount_prefix = ""
                router_self_prefix = ""
                # Extract router's own prefix: router = APIRouter(prefix="/wiki")
                self_prefix_match = re.search(r"APIRouter\s*\(\s*prefix\s*=\s*['\"]([^'\"]+)['\"]", content[:5000])
                if self_prefix_match:
                    router_self_prefix = self_prefix_match.group(1)
                # Check mount prefix map
                if fn in mount_prefixes:
                    mount_prefix = mount_prefixes[fn]
                elif "aiPlat-core" in str(fp) and fn not in ("server.py",):
                    for candidate in [os.path.basename(fp)]:
                        if candidate in mount_prefixes:
                            mount_prefix = mount_prefixes[candidate]
                            break
                # Default mount prefixes for known layers
                if not mount_prefix:
                    if "aiPlat-core" in str(fp):
                        mount_prefix = "/api/core"
                    elif "aiPlat-platform" in str(fp):
                        mount_prefix = "/api/platform"
                    elif "aiPlat-infra" in str(fp):
                        mount_prefix = "/api/infra"
                effective_prefix = mount_prefix + router_self_prefix

                for pattern, pat_type in route_patterns:
                    for m in pattern.finditer(content):
                        if pat_type in ("flask_route", "dynamic_route", "api_route"):
                            method = "ALL"  # dynamic/flask routes serve all methods
                            path = m.group(1)
                        else:
                            method, path = m.group(1).upper(), m.group(2)
                        # Apply effective prefix for router-based routes (not top-level @app routes)
                        is_top_level = bool(re.search(r"@app\.", content[:m.start()+10]))
                        # raw = route path independent of the (unreliable) MOUNT prefix,
                        # but including the router's own self-prefix. Top-level @app routes
                        # already carry their full path in the decorator.
                        if is_top_level:
                            raw_path = path
                        else:
                            raw_path = router_self_prefix + path
                        if effective_prefix and not is_top_level:
                            path = effective_prefix + path
                        entries.append({
                            "method": method,
                            "path": path,
                            "raw": raw_path,
                            "file": os.path.relpath(fp, str(WORKSPACE_ROOT)),
                            "line": content[:m.start()].count("\n") + 1,
                        })
    return entries


def _normalize_path(path: str) -> str:
    return path.rstrip("/").split("?")[0].lower()


def _paths_match(fe_path: str, be_path: str) -> bool:
    fe_norm = _normalize_path(fe_path)
    be_norm = _normalize_path(be_path)
    if fe_norm == be_norm:
        return True
    fe_segs = fe_norm.strip("/").split("/")
    be_segs = be_norm.strip("/").split("/")
    if len(fe_segs) != len(be_segs):
        return False
    for fs, bs in zip(fe_segs, be_segs):
        is_param = lambda s: bool(re.match(r'^\{.+\}$', s) or re.match(r'^<.+>$', s) or s.startswith(':'))
        if fs == bs:
            continue
        # A path param on EITHER side matches the other segment: frontend often passes a
        # concrete value (e.g. ".../trace/core") to a backend param route (".../trace/{layer}"),
        # which FastAPI routes successfully. Literal segments still anchor the match.
        if is_param(fs) or is_param(bs):
            continue
        return False
    return True


def _mismatch_sig(mm: dict) -> str:
    """Stable signature for a path mismatch (method + normalized path)."""
    return f"{mm['method'].upper()} {_normalize_path(mm['path'])}"


def _load_path_baseline() -> set:
    try:
        return {
            line.strip()
            for line in PATH_MISMATCH_BASELINE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    except Exception:
        return set()


def _write_path_baseline(signatures: set) -> None:
    PATH_MISMATCH_BASELINE.parent.mkdir(parents=True, exist_ok=True)
    PATH_MISMATCH_BASELINE.write_text("\n".join(sorted(signatures)) + "\n", encoding="utf-8")


def _compute_path_mismatches():
    """Single source of truth for §45 — frontend paths with no matching backend route.

    Returns (mismatches: list[dict], n_fe: int, n_be: int).
    n_fe == -1 → no frontend paths; n_be == -1 → no backend routes (cannot check).
    """
    fe_paths = _extract_frontend_paths()
    be_routes = _extract_backend_routes()
    if not fe_paths:
        return [], -1, 0
    if not be_routes:
        return [], len(fe_paths), -1

    seen = set()
    fe_unique = []
    for fe in fe_paths:
        key = (fe["method"], _normalize_path(fe["path"]))
        if key not in seen:
            seen.add(key)
            fe_unique.append(fe)

    mismatches = []
    for fe in fe_unique:
        pl = fe["path"].lower()
        if any(s in pl for s in ("/health", "/metrics", "/static", ".js", ".css", ".png", ".svg")):
            continue

        # Method-aware: a frontend call only matches backend routes with the same HTTP
        # method (flask "ALL" matches any). Without this the guard is method-blind — a
        # DELETE route would wrongly "satisfy" a PUT/GET frontend call on the same path.
        be_m = [be for be in be_routes if be["method"] in (fe["method"], "ALL")]
        matched = any(_paths_match(fe["path"], be["path"]) for be in be_m)
        if not matched:
            for prefix in ("/api", "/api/platform", "/platform"):
                if fe["path"].startswith(prefix + "/"):
                    stripped = fe["path"][len(prefix):]
                    if any(_paths_match(stripped, be["path"]) for be in be_m):
                        matched = True
                        break
        if not matched:
            # apiClient calls omit the configured baseURL (default "/api", see
            # apiClient.ts) — try prepending it so e.g. "/core/variables/{id}"
            # matches the mounted backend route "/api/core/variables/{variable_id}".
            for prefix in ("/api", "/api/platform"):
                if any(_paths_match(prefix + fe["path"], be["path"]) for be in be_m):
                    matched = True
                    break

        if not matched:
            # Mount-prefix-independent fallback: the guard's mount-prefix resolution
            # (_build_mount_prefixes) is unreliable for many routers. Match the frontend
            # route against backend DECORATOR paths (be["raw"], independent of where the
            # router is mounted), after stripping the frontend's deployment/routing
            # prefixes. e.g. fe "/core/runs/{id}/evaluate" → strip "/core" →
            # "/runs/{id}/evaluate" matches runs_eval.py decorator "/runs/{run_id}/evaluate".
            fe_variants = [fe["path"]]
            for prefix in ("/api/core", "/api/platform", "/api", "/core", "/platform"):
                if fe["path"].startswith(prefix + "/"):
                    fe_variants.append(fe["path"][len(prefix):])
            for v in fe_variants:
                if any(_paths_match(v, be.get("raw", be["path"])) for be in be_m):
                    matched = True
                    break

        if not matched:
            mismatches.append(fe)

    return mismatches, len(fe_unique), len(be_routes)


def check_api_path_contract() -> list[dict]:
    issues = []
    mismatches, n_fe, n_be = _compute_path_mismatches()
    if n_fe == -1:
        return [{"code": "path_contract_skip", "level": "pass",
                 "msg": "No frontend API paths found — skipping"}]
    if n_be == -1:
        return [{"code": "path_contract_skip", "level": "warning",
                 "msg": "No backend routes found — incomplete"}]

    baseline = _load_path_baseline()
    new_mm = [mm for mm in mismatches if _mismatch_sig(mm) not in baseline]
    known_mm = [mm for mm in mismatches if _mismatch_sig(mm) in baseline]

    for mm in new_mm[:20]:
        issues.append({
            "code": "path_mismatch",
            "level": "error",
            "msg": f"{mm['method']} {mm['path']} — no matching backend route (NEW — not in baseline)",
            "files": [mm["file"]],
        })
    for mm in known_mm[:20]:
        issues.append({
            "code": "path_mismatch_known",
            "level": "warning",
            "msg": f"{mm['method']} {mm['path']} — known contract debt (baseline)",
            "files": [mm["file"]],
        })

    if not mismatches:
        issues.append({"code": "path_contract_ok", "level": "pass",
                       "msg": f"All {n_fe} frontend API paths matched to backend routes"})
    else:
        issues.append({"code": "path_contract_summary", "level": "info",
                       "msg": f"Checked {n_fe} frontend paths vs {n_be} backend routes — "
                              f"{len(mismatches)} mismatches ({len(new_mm)} new, {len(known_mm)} baseline)"})
    return issues


def check_ts_import_hygiene() -> list[dict]:
    """§46: Check that frontend imports go through barrel files."""
    issues = []
    checks = [
        {
            "name": "No direct coreApi.ts imports (use services/index.ts)",
            "pattern": r"from\s+['\"].*services/coreApi['\"]",
            "path": "aiPlat-management/frontend/src",
            "exclude": ["services/index.ts", "services/coreApi.ts"],
            "level": "error",
            "msg": "Direct import from coreApi.ts — import from services/index.ts instead (§5.1)",
        },
        {
            "name": "No scattered UI imports (use components/ui)",
            "pattern": r"from\s+['\"].*components/ui/",
            "path": "aiPlat-management/frontend/src/pages",
            "exclude": [],
            "level": "warning",
            "msg": "Direct import from components/ui/ sub-file — import from components/ui barrel instead (§5.2)",
        },
    ]

    for check in checks:
        try:
            result = subprocess.run(
                ["grep", "-rEn", "--include=*.tsx", "--include=*.ts", check["pattern"],
                 check["path"]],
                capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent)
            )
            hits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            for exc in check.get("exclude", []):
                hits = [h for h in hits if exc not in h]
            for hit in hits[:10]:
                fp = hit.split(":", 2)
                issues.append({
                    "code": check["name"],
                    "level": check["level"],
                    "msg": f"{check['msg']} — {hit[:120]}",
                    "files": [],
                })
        except Exception as e:
            issues.append({"code": check["name"], "level": "warning", "msg": f"Check failed: {e}", "files": []})

    if not any(i.get("level") == "error" for i in issues):
        issues.append({"code": "ts-import-hygiene", "level": "pass", "msg": "All frontend imports follow barrel pattern"})
    return issues


# ═══════════════════════════════════════════════════════════════
# §47: FDE Route Migration Guard — detect stale /api/core/fde paths
# ═══════════════════════════════════════════════════════════════

def check_fde_route_migration() -> list[dict]:
    """Verify FDE routes are correctly registered on the core server.
    
    FDE routes ARE registered at /api/core/fde/* via:
      platform/apps/fde/__init__.py → router_registry.register("/api/core", fde_router)
      core/server.py → mount_all(app)
    
    This check verifies the chain is intact, NOT that the path should change.
    """
    issues = []
    
    # ── Phase 1: Verify router_registry chain ──
    platform_init = WORKSPACE_ROOT / "aiPlat-platform" / "apps" / "fde" / "__init__.py"
    if platform_init.exists():
        content = platform_init.read_text(encoding="utf-8")
        if 'register("/api/core", fde_router)' in content:
            issues.append({"code": "fde_register_ok", "level": "pass",
                          "msg": "FDE router registered at /api/core via platform __init__.py → router_registry"})
        else:
            issues.append({"code": "fde_register_missing", "level": "error",
                          "msg": "platform/apps/fde/__init__.py missing register('/api/core', fde_router)"})
    
    # ── Phase 2: Verify core server mounts registry ──  
    core_server = WORKSPACE_ROOT / "aiPlat-core" / "core" / "server.py"
    if core_server.exists():
        content = core_server.read_text(encoding="utf-8")
        ok = True
        if 'importlib.import_module("apps.fde")' not in content:
            issues.append({"code": "fde_import_missing", "level": "error",
                          "msg": "core/server.py missing importlib.import_module('apps.fde')"})
            ok = False
        if "mount_all(app)" not in content:
            issues.append({"code": "fde_mount_missing", "level": "error",
                          "msg": "core/server.py missing mount_all(app)"})
            ok = False
        if ok:
            issues.append({"code": "fde_mount_ok", "level": "pass",
                          "msg": "Core server correctly imports apps.fde + mount_all(app)"})
    
    # ── Phase 3: Verify frontend uses canonical /api/core/fde path ──
    frontend_src = WORKSPACE_ROOT / "aiPlat-management" / "frontend" / "src"
    if frontend_src.exists():
        found = False
        for root, dirs, files in os.walk(str(frontend_src)):
            dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".git")]
            for fn in files:
                if not fn.endswith((".ts", ".tsx")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    content = open(fp, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                m = re.search(
                    r"const\s+API\s*=\s*\([^)]*\)\s*(?::\s+\w+)?\s*=>\s*['\"`]((?:/api/[^'\"`$\n]{5,}))",
                    content
                )
                if m and "fde" in (m.group(1) or "").lower():
                    base = m.group(1).rstrip("/")
                    if base in ("/api/core/fde", "/api/platform/apps/fde"):
                        found = True
                        break
                    else:
                        issues.append({"code": "fde_wrong_base", "level": "error",
                                      "msg": f"FDE API base '{base}' should be '/api/platform/apps/fde' or '/api/core/fde'"})
            if found:
                break
        if found:
            issues.append({"code": "fde_fe_ok", "level": "pass",
                          "msg": f"Frontend uses canonical FDE API path"})
    
    if not any(i.get("level") == "error" for i in issues):
        issues.append({"code": "fde_route_ok", "level": "pass",
                      "msg": "FDE route chain: platform apps → mount_all → /api/platform/apps/fde (backward compat: /api/core/fde)"})
    return issues

def main():
    if "--write-baseline" in sys.argv:
        mismatches, _n_fe, _n_be = _compute_path_mismatches()
        sigs = {_mismatch_sig(mm) for mm in mismatches}
        _write_path_baseline(sigs)
        print(f"PASS: frontend path-mismatch baseline written = {len(sigs)} signatures")
        sys.exit(0)

    sections = [
        ("§43", "Frontend Proxy Routing", check_vite_proxy),
        ("§44", "Cross-Language API Contract", check_api_contract),
        ("§45", "Cross-Language API Path Contract", check_api_path_contract),
        ("§46", "Frontend Import Path Hygiene", check_ts_import_hygiene),
        ("§47", "FDE Route Migration Guard", check_fde_route_migration),
    ]

    total_errors = 0
    total_warnings = 0

    print("")
    print("═" * 63)
    print("  FRONTEND GUARD: Checking frontend infrastructure + contracts")
    print("═" * 63)

    for number, name, check_fn in sections:
        print("")
        print("═" * 63)
        print(f"  {number}: {name}")
        print("═" * 63)
        issues = check_fn()
        if not issues:
            print(f"  {green('[PASS]')}  no checks defined")
            continue

        has_errors = any(i.get("level") == "error" for i in issues)
        has_warnings = any(i.get("level") == "warning" for i in issues)
        has_pass = any(i.get("level") == "pass" for i in issues)

        for issue in issues:
            level = issue.get("level", "info")
            color = {"error": red, "warning": yellow, "pass": green}.get(level, lambda x: x)
            if level == "pass":
                print(f"  {color('[PASS]')}  {issue['msg']}")
                continue
            print(f"  {color(f'[{level.upper()}]')}  [{issue.get('code','?')}] {issue['msg']}")
            for f in issue.get("files", []):
                print(f"         → {f}")
            if level == "error":
                total_errors += 1
            elif level == "warning":
                total_warnings += 1

    print("")
    if total_errors:
        print(f"  {red(f'═══ FRONTEND GUARD FAILED: {total_errors} errors, {total_warnings} warnings ═══')}")
        sys.exit(1)
    elif total_warnings:
        print(f"  {yellow(f'═══ FRONTEND GUARD WARNINGS: {total_warnings} warnings ═══')}")
        sys.exit(0)
    else:
        print(f"  {green('═══ FRONTEND GUARD PASSED — all checks pass ═══')}")
        sys.exit(0)


if __name__ == "__main__":
    main()
