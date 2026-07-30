"""
Architecture Guard — extensible rules engine for codebase compliance.

Architecture:
  - Simple grep rules → YAML config (arch_guard_rules.yaml) → ArchYAMLRule
  - Complex checks → Python classes (arch_guard_rules/*.py) → ArchRule subclass
  - Both feed into ArchRegistry → run_all()

Performance:
  - Import direction checks (§1-§6) query the pre-built code graph (cached, 300s TTL)
  - Content checks (§3-§38) use graph's file index to narrow grep scope

Adding a new guard rule:
  - Simple grep: add 6 lines to arch_guard_rules.yaml, zero code change
  - Complex check: create a class in arch_guard_rules/, auto-discovered

Output:
  - Text: same format as architecture_guard.sh (backward compatible)
  - JSON: structured for /diagnostics/guard/run API
"""

from __future__ import annotations
import logging

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
        self._auto_fix = rule_def.get("auto_fix", {})

    @property
    def has_auto_fix(self) -> bool:
        """Whether this rule supports automatic template-based repair."""
        return bool(self._auto_fix.get("enabled"))

    def apply_auto_fix(self, filepath: Path, line_number: int, line_content: str) -> Tuple[bool, str]:
        """Attempt to auto-fix a violation at a specific line.

        Returns (success: bool, detail: str).
        """
        if not self.has_auto_fix:
            return False, "auto_fix not enabled"

        safety_level = self._auto_fix.get("safety_level", "low")
        pre_check_ast = self._auto_fix.get("pre_check_ast", False)
        shadow_required = self._auto_fix.get("shadow_mode_required", False)

        # Safety: pre_check_ast must pass before any fix
        if pre_check_ast:
            try:
                from scripts.guard_ast_behavior import _is_in_safe_ast_context
                if not _is_in_safe_ast_context(filepath, line_number):
                    return False, f"pre_check_ast failed: line {line_number} not in safe context"
            except Exception:
                return False, "pre_check_ast unavailable"

        # Safety: high/critical severity — block auto-fix
        if self.level in ("critical", "error") and safety_level == "high":
            return False, f"safety_level=high, level={self.level} requires human review"

        # Apply replacement
        replacement = self._auto_fix.get("replacement", "")
        if not replacement:
            return False, "no replacement pattern defined"

        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            if line_number < 1 or line_number > len(lines):
                return False, f"line {line_number} out of range (file has {len(lines)} lines)"

            target = lines[line_number - 1]
            pattern = self._check_def.get("pattern", "")
            new_line = re.sub(pattern, replacement, target)
            if new_line == target:
                return False, "pattern did not match line content"

            lines[line_number - 1] = new_line

            # Inject missing import if specified
            import_line = self._auto_fix.get("import_fix", "")
            if import_line and import_line not in content:
                lines.insert(0, import_line)

            filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True, f"fixed {filepath.name}:{line_number}"
        except Exception as e:
            return False, str(e)

    def check(self, repo_root: Path) -> List[ArchIssue]:
        dispatcher = {
            "grep_forbidden": self._check_grep_forbidden,
            "grep_required": self._check_grep_required,
            "file_exists": self._check_file_exists,
            "file_forbidden": self._check_file_forbidden,
            "cmd_output": self._check_cmd_output,
            "grep_graph_import": self._check_graph_import,
            "grep_graph": self._check_graph_grep,
            "ast_call_chain": self._check_ast_call_chain,
            "ast_field_assigned": self._check_ast_field_assigned,
        }
        handler = dispatcher.get(self._check_type)
        if handler:
            try:
                return handler(repo_root)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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
        grep_exclude_context = self._check_def.get("grep_exclude_context", 0)
        max_count = self._check_def.get("max_count", 500)
        max_matches = self._check_def.get("max_matches")  # threshold: allow up to N matches

        results = _grep(repo_root, pattern, paths, exclude, ext,
                        filename_pattern=filename_pattern,
                        grep_exclude=grep_exclude,
                        grep_exclude_context=grep_exclude_context,
                        max_count=max_count)
        if max_matches is not None and len(results) <= max_matches:
            return []  # within allowed threshold — not a violation
        if results:
            msg = self._message or f"forbidden pattern found: {pattern[:60]}"
            return [self._make_issue(msg, files=results, count=len(results))]
        return []

    def _check_grep_required(self, repo_root: Path) -> List[ArchIssue]:
        pattern = self._check_def.get("pattern", "")
        paths = self._check_def.get("paths", [])
        exclude = self._check_def.get("exclude", ["__pycache__", "tests/"])
        ext = self._check_def.get("ext", [".py"])
        min_matches = self._check_def.get("min_matches", 1)

        results = _grep(repo_root, pattern, paths, exclude, ext, max_count=min_matches * 5)
        if len(results) < min_matches:
            msg = self._message or f"required pattern not found (need {min_matches}, got {len(results)}): {pattern[:60]}"
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
        import shlex
        shell = self._check_def.get("shell", "")
        cmd = self._check_def.get("cmd", "")
        ok_pattern = self._check_def.get("ok_pattern", "^PASS")
        if shell:
            # shell pipelines / globs / ~ expansion / redirects need a real shell
            proc_cmd = ["bash", "-c", shell]
        elif isinstance(cmd, str):
            proc_cmd = shlex.split(cmd)
        else:
            proc_cmd = cmd
        result = subprocess.run(proc_cmd,
                                capture_output=True, text=True,
                                cwd=str(repo_root), timeout=120).stdout
        if re.search(ok_pattern, result):
            return []
        violations = result.strip().split("\n")
        msg = self._message or "command check failed"
        return [self._make_issue(msg, files=violations[:20], count=len(violations))]

    def _check_ast_call_chain(self, repo_root: Path) -> List[ArchIssue]:
        """Verify required_callee is reachable from entry_methods via AST call-chain analysis."""
        from core.management.ast_checks import check_call_chain
        entry_methods = self._check_def.get("entry_methods", [])
        required_callee = self._check_def.get("required_callee", "")
        max_depth = self._check_def.get("max_depth", 3)
        filepath = str(repo_root / self._check_def.get("file", ""))
        
        if not entry_methods or not required_callee:
            return [self._make_issue("ast_call_chain: missing entry_methods or required_callee")]
        
        unreachable = check_call_chain(filepath, entry_methods, required_callee, max_depth=max_depth)
        if not unreachable:
            return []
        
        msg = self._message or f"'{required_callee}' not reachable from: {', '.join(unreachable)}"
        return [self._make_issue(msg, files=[f"{filepath}:{m}" for m in unreachable], count=len(unreachable))]

    def _check_ast_field_assigned(self, repo_root: Path) -> List[ArchIssue]:
        """Verify required_field is assigned in entry_function or its sub_functions via AST analysis."""
        from core.management.ast_checks import check_field_assigned
        entry_function = self._check_def.get("entry_function", "")
        required_field = self._check_def.get("required_field", "")
        sub_functions = self._check_def.get("sub_functions", [])
        filepath = str(repo_root / self._check_def.get("file", ""))
        
        if not entry_function or not required_field:
            return [self._make_issue("ast_field_assigned: missing entry_function or required_field")]
        
        found = check_field_assigned(filepath, entry_function, required_field, sub_functions=sub_functions)
        if found:
            return []
        
        msg = self._message or f"'{required_field}' not assigned in {entry_function} or sub_functions"
        return [self._make_issue(msg, files=[filepath], count=1)]


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
        except Exception as e:
            logging.debug(str(e), exc_info=True)
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
          max_count: int = 500, grep_exclude_context: int = 0) -> List[str]:
    """Run grep across codebase, return list of 'file:line:content' strings.
    
    Uses the pre-built code graph's file index when available to avoid rglob.
    
    When grep_exclude_context > 0, a line matching the forbidden pattern is
    excluded if any of the preceding grep_exclude_context lines contain a
    grep_exclude pattern (enables 'intentionally off' comment gating).
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

            lines = content.split("\n")
            for i, line in enumerate(lines, 1):  # i is 1-indexed line number
                # grep_exclude applies to both file path and line content
                if any(re.search(ex, line) for ex in grep_exclude_set):
                    continue
                if any(re.search(ex, rel_path) for ex in grep_exclude_set):
                    continue
                if re.search(pattern, line):
                    # Context-aware exclusion: check preceding lines for exclude patterns
                    if grep_exclude_context > 0 and grep_exclude_set:
                        ctx_start = max(0, i - grep_exclude_context - 1)  # 0-indexed
                        ctx_end = i - 1  # lines before current
                        ctx_lines = lines[ctx_start:ctx_end]
                        if any(any(re.search(ex, cl) for ex in grep_exclude_set)
                               for cl in ctx_lines):
                            continue
                    text = line.strip()[:120]
                    results.append(f"{rel_path}:{i}: {text}")
                    if len(results) >= max_count:
                        return results
    return results


_SCAN_EXCLUDE_DIRS = {"__pycache__", "node_modules", ".venv", "venv", ".git", ".pytest_cache", ".mypy_cache", "dist", "build"}


def _scan_files(d: Path) -> List[Path]:
    """Fallback: scan directory with rglob, excluding cache and vendor dirs."""
    targets: List[Path] = []
    if d.is_file():
        targets = [d]
    elif d.is_dir():
        for py_file in d.rglob("*.py"):
            if any(ex in py_file.parts for ex in _SCAN_EXCLUDE_DIRS):
                continue
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

    def run_all(self, repo_root: Path, quick: bool = False) -> ArchReport:
        global _GUARD_REPORT_CACHE, _GUARD_REPORT_TS
        key = str(repo_root.resolve())
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

        # Separate grep-type rules from other rules for batched processing
        grep_rules: List[ArchYAMLRule] = []
        other_rules: List[ArchRule] = []
        for rule in self._rules:
            if (isinstance(rule, ArchYAMLRule)
                    and rule._check_def.get("type") in ("grep_forbidden", "grep_required")
                    and not rule._check_def.get("grep_graph_import")):
                grep_rules.append(rule)
            else:
                other_rules.append(rule)

        # In quick mode, only run lightweight checks: file_exists, file_forbidden
        # (No file-body grep, no graph build, no subprocess, no Python-based deep checks)
        if quick:
            grep_rules = []
            other_rules = [r for r in other_rules
                          if isinstance(r, ArchYAMLRule)
                          and r._check_def.get("type") in ("file_exists", "file_forbidden")]

        # Run batched grep rules in a single pass
        if grep_rules:
            batched_issues = self._run_grep_rules_batched(repo_root, grep_rules)
            # Distribute results back to sections
            section_map: Dict[str, Dict[str, Any]] = {}
            for rule in grep_rules:
                key = rule.section_number or rule.code
                if key not in section_map:
                    section_map[key] = {
                        "number": rule.section_number or key,
                        "name": rule.section_name or key,
                        "status": "pass",
                        "items": [],
                    }
                issues = batched_issues.get(rule.code, [])
                section_map[key]["items"].extend(issues)
                for issue in issues:
                    if issue.level == "error":
                        section_map[key]["status"] = "fail"
                        total_violations += issue.count or 1

            for key, sec_data in section_map.items():
                sstatus = sec_data["status"]
                if sstatus == "fail":
                    fail_count += 1
                elif any(i.level == "warning" for i in sec_data["items"]):
                    warn_count += 1
                else:
                    pass_count += 1
                sections.append(ArchSection(
                    number=sec_data["number"], name=sec_data["name"],
                    status=sstatus, items=sec_data["items"],
                ))

        # Run remaining rules as before (non-grep, graph-grep, complex)
        section_map: Dict[str, List[ArchRule]] = {}
        for rule in other_rules:
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
        if _GUARD_REPORT_CACHE is None:
            _GUARD_REPORT_CACHE = {}
        _GUARD_REPORT_CACHE[key] = {"report": report, "_ts": time.time()}
        return report

    def _run_grep_rules_batched(self, repo_root: Path,
                                 rules: List[ArchYAMLRule]) -> Dict[str, List[ArchIssue]]:
        """Run multiple grep rules in a single file-walk pass.

        Groups rules by (paths, ext, exclude) signature. For each group,
        walks files once, reads each file once, tests ALL patterns per line.
        """
        rule_configs = []
        for rule in rules:
            rc = {
                "code": rule.code,
                "message": rule._message or "",
                "level": rule.level,
                "pattern": rule._check_def.get("pattern", ""),
                "paths": tuple(rule._check_def.get("paths", [])),
                "exclude": tuple(rule._check_def.get("exclude", ["__pycache__", "tests/", ".git", "node_modules"])),
                "ext": tuple(rule._check_def.get("ext", [".py"])),
                "filename_pattern": rule._check_def.get("filename_pattern"),
                "grep_exclude": tuple(rule._check_def.get("grep_exclude", [])),
                "max_count": rule._check_def.get("max_count", 500),
                "max_matches": rule._check_def.get("max_matches"),
                "min_matches": rule._check_def.get("min_matches", 1),
                "check_type": rule._check_def.get("type", "grep_forbidden"),
                "grep_exclude_context": rule._check_def.get("grep_exclude_context", 0),
            }
            if rc["pattern"]:
                rule_configs.append(rc)

        if not rule_configs:
            return {}

        # Group rules by (paths, ext, exclude) — same file set → batch together
        groups: Dict[tuple, List[dict]] = {}
        for rc in rule_configs:
            sig = (rc["paths"], rc["ext"], rc["exclude"], rc["filename_pattern"] or "")
            groups.setdefault(sig, []).append(rc)

        # Per-rule results
        results: Dict[str, List[str]] = {rc["code"]: [] for rc in rule_configs}

        # Process each group with a single file walk
        for sig, group_rules in groups.items():
            paths, exts, excludes, fname_pat = sig
            exts_set = set(exts)
            excludes_set = set(excludes)

            # Collect files for this group
            files: List[Path] = []
            for search_path in paths:
                d = repo_root / search_path
                if not d.exists():
                    continue
                try:
                    adapter = _get_graph_adapter(repo_root)
                    adapter._ensure_loaded()
                    if adapter._nodes:
                        path_prefix = search_path.lstrip("/").rstrip("/")
                        targets = [f for f in adapter.graph_indexed_files()
                                  if str(f.relative_to(repo_root)).startswith(path_prefix)
                                  and (not exts_set or any(str(f).endswith(e) for e in exts_set))]
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
                    if any(x in rel_path for x in excludes_set):
                        continue
                    if exts_set and not any(rel_path.endswith(e) for e in exts_set):
                        continue
                    if fname_pat and not re.search(fname_pat, rel_path):
                        continue
                    files.append(py_file)

            # Deduplicate
            seen_paths = set()
            files = [f for f in files if not (str(f) in seen_paths or seen_paths.add(str(f)))]

            # Prepare per-rule compiled patterns and limit tracking
            for rc in group_rules:
                rc["_pattern_re"] = re.compile(rc["pattern"])
                rc["_grep_exclude_re"] = [re.compile(ex) for ex in (rc["grep_exclude"] or ())]
                rc["_done"] = False

            # Single pass: read each file once, test all rules' patterns
            for py_file in files:
                rel_path = str(py_file.relative_to(repo_root))
                try:
                    content = py_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                active_rules = [rc for rc in group_rules if not rc["_done"]]
                if not active_rules:
                    break

                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    for rc in active_rules:
                        if rc["_done"]:
                            continue
                        # Apply grep_exclude to line and path
                        if rc["_grep_exclude_re"]:
                            if any(ex.search(line) for ex in rc["_grep_exclude_re"]):
                                continue
                            if any(ex.search(rel_path) for ex in rc["_grep_exclude_re"]):
                                continue
                        if rc["_pattern_re"].search(line):
                            # Context-aware exclusion: check preceding lines
                            ctx_n = rc.get("grep_exclude_context", 0)
                            if ctx_n > 0 and rc["_grep_exclude_re"]:
                                ctx_start = max(0, i - ctx_n - 1)
                                ctx_lines = lines[ctx_start:i-1]
                                if any(any(ex.search(cl) for ex in rc["_grep_exclude_re"])
                                       for cl in ctx_lines):
                                    continue
                            results[rc["code"]].append(
                                f"{rel_path}:{i}: {line.strip()[:120]}")
                            limit = rc["max_count"]
                            if limit > 0 and len(results[rc["code"]]) >= limit:
                                rc["_done"] = True
                # Clean up compiled patterns
                for rc in active_rules:
                    if rc.get("_done"):
                        rc.pop("_pattern_re", None)
                        rc.pop("_grep_exclude_re", None)

            # Clean up remaining
            for rc in group_rules:
                rc.pop("_pattern_re", None)
                rc.pop("_grep_exclude_re", None)
                rc.pop("_done", None)

        # Convert to ArchIssue per rule
        output: Dict[str, List[ArchIssue]] = {}
        for rc in rule_configs:
            rule_results = results[rc["code"]]
            code = rc["code"]
            if rc["check_type"] == "grep_required":
                if len(rule_results) < rc["min_matches"]:
                    msg = rc["message"] or f"required pattern not found (need {rc['min_matches']}, got {len(rule_results)})"
                    output[code] = [ArchIssue(level=rc["level"], code=code,
                                              message=msg, count=1)]
                else:
                    output[code] = []
            else:
                if rc["max_matches"] is not None and len(rule_results) <= rc["max_matches"]:
                    output[code] = []
                elif rule_results:
                    msg = rc["message"] or f"forbidden pattern found: {rc['pattern'][:60]}"
                    output[code] = [ArchIssue(level=rc["level"], code=code,
                                              message=msg, files=rule_results,
                                              count=len(rule_results))]
                else:
                    output[code] = []

        return output

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
        except Exception as e:
            logging.debug(str(e), exc_info=True)

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
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
        except Exception as e:
            logging.debug(str(e), exc_info=True)


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
