"""
sys_code - Code search syscalls.

Atomic code search operations that go through the Gate system:
- sys_glob: find files matching a glob pattern
- sys_code_search: grep-style content search across code files

Each syscall passes through TraceGate (audit) and workspace scoping.
"""

from __future__ import annotations
import logging

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.infrastructure.gates import TraceGate
from core.harness.kernel.execution_context import get_active_workspace_context

_EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".eggs", ".mypy_cache"}


def _resolve_search_root() -> str:
    try:
        ws = get_active_workspace_context()
        if ws:
            return os.path.realpath(os.path.expanduser(
                getattr(ws, "workspace_path", None) or os.getcwd()
            ))
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return os.path.realpath(os.getcwd())


async def sys_glob(
    pattern: str,
    *,
    root: str = "",
    max_results: int = 200,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Find files matching a glob pattern.

    Supports ** for recursive matching. Returns dict with: success, files, count, error.
    """
    gate = TraceGate.start("sys.glob", trace_context)
    try:
        search_root = os.path.realpath(root) if root else _resolve_search_root()
        files: List[str] = []

        if "**" in pattern:
            for dirpath, dirnames, filenames in os.walk(search_root):
                dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")]
                for fname in filenames:
                    rel = os.path.relpath(os.path.join(dirpath, fname), search_root)
                    if _match_glob(rel, pattern):
                        files.append(rel)
                        if len(files) >= max_results:
                            break
                if len(files) >= max_results:
                    break
        else:
            for fname in os.listdir(search_root):
                fpath = os.path.join(search_root, fname)
                if os.path.isfile(fpath) and _match_glob(fname, pattern):
                    files.append(fname)
                    if len(files) >= max_results:
                        break

        return {"success": True, "files": files, "count": len(files), "root": search_root}
    except Exception as e:
        return {"success": False, "error": str(e), "files": []}
    finally:
        gate.close()


async def sys_code_search(
    pattern: str,
    *,
    path: str = "",
    include: str = "",
    max_results: int = 100,
    trace_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Grep-style content search across code files.

    pattern: regex pattern to search for
    path: directory to search in (default: workspace root)
    include: file glob filter (e.g. "*.py", "*.{ts,tsx}")
    max_results: maximum matches to return

    Returns dict with: success, matches (list of {file, line, content}), count, error.
    """
    gate = TraceGate.start("sys.code_search", trace_context)
    try:
        search_root = os.path.realpath(path) if path else _resolve_search_root()
        if not os.path.isdir(search_root):
            return {"success": False, "error": f"Directory not found: {search_root}", "matches": []}

        compiled = re.compile(pattern, re.IGNORECASE)
        include_patterns = [p.strip() for p in include.split(",")] if include else []
        matches: List[Dict[str, Any]] = []

        for dirpath, dirnames, filenames in os.walk(search_root):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")]
            for fname in filenames:
                if include_patterns:
                    if not any(fnmatch.fnmatch(fname, p) for p in include_patterns):
                        continue
                fpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(fpath, search_root)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        for lineno, line in enumerate(f, 1):
                            if compiled.search(line):
                                matches.append({
                                    "file": rel,
                                    "line": lineno,
                                    "content": line.strip()[:200],
                                })
                                if len(matches) >= max_results:
                                    break
                    if len(matches) >= max_results:
                        break
                except (PermissionError, OSError):
                    continue
                if len(matches) >= max_results:
                    break

        return {"success": True, "matches": matches, "count": len(matches), "root": search_root}
    except re.error as e:
        return {"success": False, "error": f"Invalid regex: {e}", "matches": []}
    except Exception as e:
        return {"success": False, "error": str(e), "matches": []}
    finally:
        gate.close()


def _match_glob(name: str, pattern: str) -> bool:
    # Normalize path separators for cross-platform matching
    return fnmatch.fnmatch(name.replace(os.sep, "/"), pattern.replace(os.sep, "/"))


__all__ = ["sys_glob", "sys_code_search"]
