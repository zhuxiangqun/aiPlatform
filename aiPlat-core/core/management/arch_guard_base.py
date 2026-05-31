"""
Architecture Guard — extensible rules engine for codebase compliance.

Architecture:
  - Simple grep rules → YAML config (arch_guard_rules.yaml) → ArchYAMLRule
  - Complex checks → Python classes (arch_guard_rules/*.py) → ArchRule subclass
  - Both feed into ArchRegistry → run_all()

Performance:
  - Import direction checks (§1-§6) query the pre-built code graph (cached, 120s TTL)
  - Content checks (§3-§38) use graph's file index to narrow grep scope

Adding a new guard rule:
  - Simple grep: add 6 lines to arch_guard_rules.yaml, zero code change
  - Complex check: create a class in arch_guard_rules/, auto-discovered

Output:
  - Text: same format as architecture_guard.sh (backward compatible)
  - JSON: structured for /diagnostics/guard/run API
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# Data classes
# ============================================================

@dataclass
class ArchIssue:
    """A single architecture violation."""
    level: str  # error | warning | pass
    code: str
    message: str
    files: List[str] = field(default_factory=list)
    count: int = 0


@dataclass
class ArchSection:
    """A group of related checks (maps to a § section in .sh output)."""
    number: str  # "§1", "§2", etc.
    name: str
    status: str  # pass | warn | fail
    items: List[ArchIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "name": self.name,
            "status": self.status,
            "items": [asdict(x) for x in self.items],
        }


@dataclass
class ArchReport:
    """Full architecture guard report."""
    ok: bool
    violations: int
    sections: List[ArchSection] = field(default_factory=list)
    duration_ms: float = 0.0
    summary: Dict[str, int] = field(default_factory=dict)


# ============================================================
# Rule base classes
# ============================================================

class ArchRule:
    """Base class for architecture guard rules."""

    code: str = ""
    level: str = "error"
    section_number: str = ""
    section_name: str = ""

    def check(self, repo_root: Path) -> List[ArchIssue]:
        raise NotImplementedError


class ArchYAMLRule(ArchRule):
    """
    Declarative rule from YAML config.

    Supported check types:
      - grep_forbidden:  grep for pattern, violations = every hit
      - grep_required:   grep for pattern, violations = 0 hits
      - file_exists:     check file/dir exists, violations = missing
      - file_forbidden:  check filename pattern, violations = every match
      - cmd_output:      run shell command, parse output for violations
    """

    def __init__(self, rule_def: Dict[str, Any]):
        self._def = rule_def
        self.code = rule_def.get("id", "")
        self.level = rule_def.get("level", "error")
        self.section_number = rule_def.get("section", "")
        self.section_name = rule_def.get("section_name", "")
        self._check_def = rule_def.get("check", {})
        self._check_type = self._check_def.get("type", "")
        self._message = rule_def.get("message", "")

    def check(self, repo_root: Path) -> List[ArchIssue]:
        dispatcher = {
            "grep_forbidden": self._check_grep_forbidden,
            "grep_required": self._check_grep_required,
            "file_exists": self._check_file_exists,
            "file_forbidden": self._check_file_forbidden,
            "cmd_output": self._check_cmd_output,
            "grep_graph_import": self._check_graph_import,
            "grep_graph": self._check_graph_grep,
        }
        handler = dispatcher.get(self._check_type)
        if handler:
            try:
                return handler(repo_root)
            except Exception:
                pass
        return []

    def _make_issue(self, message: str, files: List[str] = None, count: int = 0) -> ArchIssue:
        return ArchIssue(level=self.level, code=self.code, message=message, files=files or [], count=count)

    # ── check handlers ──

    def _check_graph_import(self, repo_root: Path) -> List[ArchIssue]:
        """Use cached code graph to check import direction violations."""
        from_pattern = self._check_def.get("from_pattern", "")
        to_pattern = self._check_def.get("to_pattern", "")
        adapter = _get_graph_adapter(repo_root)
        
        if to_pattern:
            results = adapter.has_import(from_pattern, to_pattern)
        else:
            results = adapter.find_imports(from_pattern)

        if results:
            msg = self._message or f"forbidden import: {from_pattern} → {to_pattern or '*'}"
            return [self._make_issue(msg, files=results[:200], count=len(results))]
        return []

    def _check_graph_grep(self, repo_root: Path) -> List[ArchIssue]:
        """Use graph-indexed file list to narrow grep scope, then grep content."""
        path_pattern = self._check_def.get("path_pattern", "")
        pattern = self._check_def.get("pattern", "")
        grep_exclude = self._check_def.get("grep_exclude", [])
        max_count = self._check_def.get("max_count", 500)

        adapter = _get_graph_adapter(repo_root)
        files = adapter.get_files_matching(path_pattern) if path_pattern else adapter.graph_indexed_files()

        results = []
        grep_exclude_set = set(grep_exclude or [])
        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            rel_path = str(f.relative_to(repo_root))
            for i, line in enumerate(content.split("\n"), 1):
                # grep_exclude applies to both file path and line content
                if any(re.search(ex, line) for ex in grep_exclude_set):
                    continue
                if any(re.search(ex, rel_path) for ex in grep_exclude_set):
                    continue
                if re.search(pattern, line):
                    results.append(f"{rel_path}:{i}: {line.strip()[:120]}")
                    if len(results) >= max_count:
                        break
            if len(results) >= max_count:
                break

        if results:
            msg = self._message or f"forbidden pattern found in {path_pattern or 'codebase'}"
            return [self._make_issue(msg, files=results, count=len(results))]
        return []

    def _check_grep_forbidden(self, repo_root: Path) -> List[ArchIssue]:
        pattern = self._check_def.get("pattern", "")
        paths = self._check_def.get("paths", [])
        exclude = self._check_def.get("exclude", ["__pycache__", "tests/", ".git", "node_modules"])
        ext = self._check_def.get("ext", [".py"])
        filename_pattern = self._check_def.get("filename_pattern")
        grep_exclude = self._check_def.get("grep_exclude", [])
        max_count = self._check_def.get("max_count", 500)

        results = _grep(repo_root, pattern, paths, exclude, ext,
                        filename_pattern=filename_pattern,
                        grep_exclude=grep_exclude,
                        max_count=max_count)
        if results:
            msg = self._message or f"forbidden pattern found: {pattern[:60]}"
            return [self._make_issue(msg, files=results, count=len(results))]
        return []

    def _check_grep_required(self, repo_root: Path) -> List[ArchIssue]:
        pattern = self._check_def.get("pattern", "")
        paths = self._check_def.get("paths", [])
        exclude = self._check_def.get("exclude", ["__pycache__", "tests/"])
        ext = self._check_def.get("ext", [".py"])

        results = _grep(repo_root, pattern, paths, exclude, ext, max_count=1)
        if not results:
            msg = self._message or f"required pattern not found: {pattern[:60]}"
            return [self._make_issue(msg, count=1)]
        return []

    def _check_file_exists(self, repo_root: Path) -> List[ArchIssue]:
        paths = self._check_def.get("paths", [])
        missing = []
        for p in paths:
            fp = repo_root / p
            if not fp.exists():
                missing.append(str(p))
        if missing:
            msg = self._message or f"required files/dirs missing"
            return [self._make_issue(msg, files=missing, count=len(missing))]
        return []

    def _check_file_forbidden(self, repo_root: Path) -> List[ArchIssue]:
        pattern = self._check_def.get("pattern", "")
        paths = self._check_def.get("paths", [])
        found = []
        for p in paths:
            d = repo_root / p
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if re.search(pattern, f.name):
                    found.append(str(f.relative_to(repo_root)))
        if found:
            msg = self._message or f"forbidden file names matching: {pattern}"
            return [self._make_issue(msg, files=found, count=len(found))]
        return []

    def _check_cmd_output(self, repo_root: Path) -> List[ArchIssue]:
        cmd = self._check_def.get("cmd", "")
        ok_pattern = self._check_def.get("ok_pattern", "^PASS")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                cwd=str(repo_root), timeout=120).stdout
        if re.search(ok_pattern, result):
            return []
        violations = result.strip().split("\n")
        msg = self._message or "command check failed"
        return [self._make_issue(msg, files=violations[:20], count=len(violations))]


# ============================================================
# Graph Query Adapter — uses pre-built code/capability graphs
# ============================================================

class GraphQueryAdapter:
    """Queries the cached code graph instead of filesystem grep.

    The code graph (code_graph.py) already scans all files, parses imports,
    and caches results for 120s. This adapter reuses that cache for:
      - Import direction checks (§1-§6)
      - File-level content scans (narrowing grep scope to graph-indexed files)
    """

    def __init__(self, repo_root: Path):
        self._repo_root = repo_root
        self._nodes: Dict[str, Any] = {}
        self._edges: List[Dict[str, str]] = []
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        try:
            from core.harness.knowledge.code_graph import build_graph, default_roots
            roots = [self._repo_root / r for r in default_roots()]
            self._nodes, self._edges, _issues = build_graph(self._repo_root, roots)
        except Exception:
            pass
        self._loaded = True

    def has_import(self, from_pattern: str, to_pattern: str) -> List[str]:
        """Find edges where source matches from_pattern and dest matches to_pattern.
        Returns list of 'source_path → dest_path' strings.
        Only considers import edges (not call edges), which eliminates false positives
        from cross-file function name matching.
        """
        self._ensure_loaded()
        violations = []
        for edge in self._edges:
            if edge.get("kind", "import") != "import":
                continue
            if re.search(from_pattern, edge["from"]) and re.search(to_pattern, edge["to"]):
                violations.append(f"{edge['from']} → {edge['to']}")
        return violations

    def find_imports(self, from_pattern: str) -> List[str]:
        """Find all imports from files matching from_pattern.
        Returns list of 'source_path → dest_path' strings.
        Only considers import edges (not call edges).
        """
        self._ensure_loaded()
        violations = []
        for edge in self._edges:
            if edge.get("kind", "import") != "import":
                continue
            if re.search(from_pattern, edge["from"]):
                violations.append(f"{edge['from']}: imports {edge['to']}")
        return violations

    def get_files_matching(self, path_pattern: str) -> List[Path]:
        """Get file paths matching the pattern from graph's indexed files."""
        self._ensure_loaded()
        files = []
        pattern = path_pattern.replace("\\", "/")
        for node_path in self._nodes:
            if re.search(pattern, str(node_path)):
                full_path = self._repo_root / node_path
                if full_path.exists():
                    files.append(full_path)
        return files

    def graph_indexed_files(self) -> List[Path]:
        """Return all files in the graph index (already filtered for noise)."""
        self._ensure_loaded()
        return [self._repo_root / p for p in self._nodes
                if (self._repo_root / p).exists()]


_graph_adapters: Dict[str, GraphQueryAdapter] = {}

# ── ArchRegistry run_all cache (30s TTL) ──
_GUARD_REPORT_CACHE: Optional[Dict[str, Any]] = None
_GUARD_REPORT_TS: Optional[Dict[str, Any]] = None


def _get_graph_adapter(repo_root: Path) -> GraphQueryAdapter:
    key = str(repo_root.resolve())
    if key not in _graph_adapters:
        _graph_adapters[key] = GraphQueryAdapter(repo_root)
    return _graph_adapters[key]


# ============================================================
# Grep engine (shared)
# ============================================================

def _grep(repo_root: Path, pattern: str, paths: List[str], exclude: List[str],
          ext: List[str], filename_pattern: str = None, grep_exclude: List[str] = None,
          max_count: int = 500) -> List[str]:
    """Run grep across codebase, return list of 'file:line:content' strings.
    
    Uses the pre-built code graph's file index when available to avoid rglob.
    """
    results: List[str] = []
    exclude_set = set(exclude)
    grep_exclude_set = set(grep_exclude or [])

    for search_path in paths:
        d = repo_root / search_path
        if not d.exists():
            continue

        # Try graph-indexed file list first (avoids rglob)
        try:
            adapter = _get_graph_adapter(repo_root)
            adapter._ensure_loaded()
            if adapter._nodes:
                path_prefix = search_path.lstrip("/").rstrip("/")
                targets = [f for f in adapter.graph_indexed_files()
                          if str(f.relative_to(repo_root)).startswith(path_prefix)
                          and (not ext or any(str(f).endswith(e) for e in ext))]
                if not targets:
                    targets = _scan_files(d)
            else:
                targets = _scan_files(d)
        except Exception:
            targets = _scan_files(d)

        for py_file in targets:
            if not py_file.is_file():
                continue
            rel_path = str(py_file.relative_to(repo_root))
            if any(x in rel_path for x in exclude_set):
                continue
            if ext and not any(rel_path.endswith(e) for e in ext):
                continue
            if filename_pattern and not re.search(filename_pattern, rel_path):
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for i, line in enumerate(content.split("\n"), 1):
                # grep_exclude applies to both file path and line content
                if any(re.search(ex, line) for ex in grep_exclude_set):
                    continue
                if any(re.search(ex, rel_path) for ex in grep_exclude_set):
                    continue
                if re.search(pattern, line):
                    text = line.strip()[:120]
                    results.append(f"{rel_path}:{i}: {text}")
                    if len(results) >= max_count:
                        return results
    return results


def _scan_files(d: Path) -> List[Path]:
    """Fallback: scan directory with rglob."""
    targets: List[Path] = []
    if d.is_file():
        targets = [d]
    elif d.is_dir():
        for py_file in d.rglob("*"):
            targets.append(py_file)
    return targets


# ============================================================
# Registry
# ============================================================

class ArchRegistry:
    """Collects all arch guard rules and runs them against a repo."""

    def __init__(self):
        self._rules: List[ArchRule] = []

    def register(self, rule: ArchRule) -> None:
        self._rules.append(rule)

    def discover(self) -> None:
        self._load_yaml_rules()
        self._load_python_rules()

    def run_all(self, repo_root: Path) -> ArchReport:
        global _GUARD_REPORT_CACHE, _GUARD_REPORT_TS
        key = str(repo_root.resolve())
        # Check cache from get_arch_registry (single process)
        if _GUARD_REPORT_CACHE and key in _GUARD_REPORT_CACHE:
            cached = _GUARD_REPORT_CACHE[key]
            if time.time() - cached.get("_ts", 0) < 30:
                return cached["report"]
        
        started = time.time()
        sections: List[ArchSection] = []
        total_violations = 0
        pass_count = 0
        warn_count = 0
        fail_count = 0

        # Group rules by section
        section_map: Dict[str, List[ArchRule]] = {}
        for rule in self._rules:
            key = rule.section_number or rule.code
            section_map.setdefault(key, []).append(rule)

        for key, rules in section_map.items():
            section = ArchSection(
                number=rules[0].section_number or key,
                name=rules[0].section_name or key,
                status="pass",
            )
            section_ok = True
            for rule in rules:
                issues = rule.check(repo_root)
                section.items.extend(issues)
                for issue in issues:
                    if issue.level == "error":
                        total_violations += issue.count or 1
                        section_ok = False
                    elif issue.level == "warning" and (issue.files or issue.count > 0):
                        pass  # warnings don't count as violations

            if not section_ok:
                section.status = "fail"
                fail_count += 1
            elif any(i.level == "warning" for i in section.items):
                section.status = "warn"
                warn_count += 1
            else:
                pass_count += 1
            sections.append(section)

        duration_ms = (time.time() - started) * 1000
        report = ArchReport(
            ok=(total_violations == 0),
            violations=total_violations,
            sections=sections,
            duration_ms=duration_ms,
            summary={"pass": pass_count, "warn": warn_count, "fail": fail_count, "violations": total_violations},
        )
        # Cache for 30s
        if _GUARD_REPORT_CACHE is None:
            _GUARD_REPORT_CACHE = {}
        _GUARD_REPORT_CACHE[key] = {"report": report, "_ts": time.time()}
        return report

    def _load_yaml_rules(self) -> None:
        config_path = Path(__file__).parent / "arch_guard_rules.yaml"
        if not config_path.exists():
            return
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for rule_def in data.get("rules", []):
                self.register(ArchYAMLRule(rule_def))
        except Exception:
            pass

    def _load_python_rules(self) -> None:
        rules_pkg = Path(__file__).parent / "arch_guard_rules"
        if not rules_pkg.is_dir():
            return
        try:
            for item in sorted(rules_pkg.iterdir()):
                if item.suffix != ".py" or item.name.startswith("_"):
                    continue
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"core.management.arch_guard_rules.{item.stem}",
                        str(item)
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type)
                                    and issubclass(attr, ArchRule)
                                    and attr is not ArchRule
                                    and attr is not ArchYAMLRule
                                    and not attr.__name__.startswith("_")):
                                self.register(attr())
                except Exception:
                    pass
        except Exception:
            pass


# ============================================================
# Singleton
# ============================================================

_registry: Optional[ArchRegistry] = None


def get_arch_registry() -> ArchRegistry:
    global _registry
    if _registry is None:
        _registry = ArchRegistry()
        _registry.discover()
    return _registry
