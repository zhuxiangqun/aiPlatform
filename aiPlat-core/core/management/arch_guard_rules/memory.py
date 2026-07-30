"""Memory anti-pattern detection rules — catches unbounded collections.

§83: Detects global/class-level containers without size limits, TTL, or cleanup
     that could grow unboundedly and cause memory leaks over time.
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from core.management.arch_guard_base import ArchIssue, ArchRule

_SCAN_PATHS = ["aiPlat-core/core", "aiPlat-infra/infra"]
_EXCLUDE_DIRS = {
    "__pycache__", "node_modules", ".venv", "venv", ".git",
    ".pytest_cache", ".mypy_cache", "dist", "build",
}


def _iter_py_files(repo_root: Path) -> List[Path]:
    files = []
    for sp in _SCAN_PATHS:
        d = repo_root / sp
        if not d.is_dir():
            continue
        for py_file in d.rglob("*.py"):
            if any(ex in py_file.parts for ex in _EXCLUDE_DIRS):
                continue
            if "/tests/" in str(py_file) or "/test_" in str(py_file.name):
                continue
            files.append(py_file)
    return files


class GlobalDictNoCleanupCheck(ArchRule):
    """§83a: Class-level or module-level dict declarations without cleanup mechanism.

    Detects patterns like:
      _cache: Dict[str, Any] = {}        ← no clear(), max_size, TTL
      self._items: Dict[str, ...] = {}   ← no pop/del in scope
    """

    code = "memory_global_dict_no_cleanup"
    level = "warning"
    section_number = "§83"
    section_name = "Memory Anti-Pattern Detection"

    def check(self, repo_root: Path) -> List[ArchIssue]:
        violations = []
        for py_file in _iter_py_files(repo_root):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Find Dict[str, ...] = {} declarations
            dict_matches = list(re.finditer(
                r'(?:Dict\[str\s*,\s*[A-Za-z\[\],\s]+\]\s*=\s*\{\})',
                content,
            ))
            if not dict_matches:
                continue

            rel_path = str(py_file.relative_to(repo_root))

            # Check if the file has cleanup mechanisms
            has_cleanup = bool(re.search(
                r'\.clear\(\)|max_size|ttl|_maybe_cleanup|_MAX_CACHE|_IDLE_TTL|_loaded_instances',
                content,
            ))
            # Count eviction patterns (pop, del, .clear)
            evictions = len(re.findall(r'\.pop\(|del\s+\w+\[|\.clear\(\)', content))

            if not has_cleanup and evictions < 2:
                line_nums = []
                for m in dict_matches[:3]:
                    line_no = content[:m.start()].count("\n") + 1
                    line_nums.append(str(line_no))

                violations.append(
                    f"{rel_path}:{','.join(line_nums)}: "
                    f"class/module-level dict without size limit/TTL/cleanup"
                )

        if violations:
            return [
                ArchIssue(
                    level=self.level,
                    code=self.code,
                    message=(
                        f"Dict containers without cleanup (max_size, TTL, clear, pop, del): "
                        f"{len(violations)} file(s). "
                        f"Add max_size/TTL/cleanup to prevent unbounded growth."
                    ),
                    files=violations[:30],
                    count=len(violations),
                )
            ]
        return []


class UnboundedAppendCheck(ArchRule):
    """§83b: Files with many .append() calls but no .clear() or size guard.

    Detects accumulation patterns:
      results.append(x)         ← growing list, never cleared
      items.append(item)        ← no max_len guard
    """

    code = "memory_unbounded_append"
    level = "warning"
    section_number = "§83"
    section_name = "Memory Anti-Pattern Detection"

    def check(self, repo_root: Path) -> List[ArchIssue]:
        violations = []
        for py_file in _iter_py_files(repo_root):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            appends = len(re.findall(r'\.append\(', content))
            clears = len(re.findall(r'\.clear\(\)', content))
            size_guards = len(re.findall(
                r'max_|MAX_|len\(.*\s*[><=!]+\s*\d+',
                content,
            ))

            if appends > 5 and clears == 0 and size_guards < 2:
                rel_path = str(py_file.relative_to(repo_root))
                violations.append(f"{rel_path}: {appends} .append() calls, no .clear() or size guard")

        if violations:
            return [
                ArchIssue(
                    level=self.level,
                    code=self.code,
                    message=(
                        f"Unbounded list growth: {len(violations)} file(s) "
                        f"with 5+ .append() but no .clear() or size guard."
                    ),
                    files=violations[:30],
                    count=len(violations),
                )
            ]
        return []


class LRUCacheNoClearCheck(ArchRule):
    """§83c: @lru_cache / @cache usage without matching cache_clear() call.

    Caches without explicit clear() can hold references to dead objects,
    preventing garbage collection.
    """

    code = "memory_lru_cache_no_clear"
    level = "warning"
    section_number = "§83"
    section_name = "Memory Anti-Pattern Detection"

    def check(self, repo_root: Path) -> List[ArchIssue]:
        violations = []
        for py_file in _iter_py_files(repo_root):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            has_lru = bool(re.search(r'@lru_cache|@functools\.cache|@cache\b', content))
            has_clear = bool(re.search(r'cache_clear\(\)', content))

            if has_lru and not has_clear:
                rel_path = str(py_file.relative_to(repo_root))
                violations.append(
                    f"{rel_path}: has @lru_cache/@cache but no cache_clear() call"
                )

        if violations:
            return [
                ArchIssue(
                    level=self.level,
                    code=self.code,
                    message=(
                        f"LRU caches without clear(): {len(violations)} file(s) "
                        f"use @lru_cache without explicit cache_clear()."
                    ),
                    files=violations[:30],
                    count=len(violations),
                )
            ]
        return []
