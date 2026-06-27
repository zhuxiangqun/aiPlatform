"""
RepositoryMap — scan a project directory and produce a compact structural map.

Inspired by Aider's repo-map: compresses a full project tree, symbol table,
and cross-reference graph into a token-efficient prompt insert (~500 tokens).

Usage:
    rmap = RepositoryMap()
    result = rmap.scan("/path/to/project")
    prompt_text = rmap.to_prompt(result)
"""

from __future__ import annotations
import logging

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class FileSymbol:
    name: str
    kind: str  # "class", "function", "module"
    line: int


@dataclass
class FileRef:
    source: str
    target: str
    kind: str  # "import", "from_import"


@dataclass
class FileEntry:
    path: str          # relative to repo root
    size: int          # bytes
    symbols: List[FileSymbol] = field(default_factory=list)
    imports_from: Set[str] = field(default_factory=set)


@dataclass
class RepoMapResult:
    root: str
    files: List[FileEntry] = field(default_factory=list)
    refs: List[FileRef] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_symbols(self) -> int:
        return sum(len(f.symbols) for f in self.files)


class RepositoryMap:
    def __init__(self, max_files: int = 200, max_depth: int = 5):
        self._max_files = max_files
        self._max_depth = max_depth
        self._skip_patterns = re.compile(
            r"(\.git|__pycache__|node_modules|\.venv|\.env|\.pytest_cache|\.mypy_cache|"
            r"dist|build|\.egg-info|site-packages)"
        )

    def scan(self, repo_root: str) -> RepoMapResult:
        root = os.path.abspath(repo_root)
        result = RepoMapResult(root=root)
        rpath = Path(root)

        for py_file in sorted(rpath.rglob("*.py"))[:self._max_files]:
            rel = str(py_file.relative_to(rpath))
            if self._skip_patterns.search(rel) or rel.startswith("."):
                continue
            if rel.count(os.sep) > self._max_depth:
                continue

            entry = FileEntry(
                path=rel,
                size=py_file.stat().st_size,
            )
            try:
                code = py_file.read_text(encoding="utf-8", errors="ignore")
                entry.symbols = self._extract_symbols(code)
                entry.imports_from = self._extract_imports(code)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

            result.files.append(entry)
            for imp in entry.imports_from:
                result.refs.append(FileRef(source=rel, target=imp, kind="from_import"))

        return result

    def to_prompt(self, result: RepoMapResult, max_tokens: int = 500) -> str:
        """Compress repo map into a prompt-suitable summary."""
        lines = [f"## Repository Map ({result.total_files} files, {result.total_symbols} symbols)"]
        tokens_est = 0

        # Tree summary
        dirs = sorted(set(os.path.dirname(f.path) or "." for f in result.files))
        for d in dirs[:15]:
            count = sum(1 for f in result.files if os.path.dirname(f.path) == d or (d == "." and os.path.dirname(f.path) == ""))
            lines.append(f"  {d}/ ({count} files)")
            tokens_est += len(lines[-1]) // 4

        if tokens_est > max_tokens * 0.7:
            return "\n".join(lines)[:max_tokens * 4]

        # Top symbols per file
        for f in result.files[:20]:
            if f.symbols:
                syms = ", ".join(f"{s.kind[0]}:{s.name}" for s in f.symbols[:5])
                lines.append(f"  {f.path}: {syms}")
                tokens_est += len(lines[-1]) // 4
                if tokens_est > max_tokens * 0.95:
                    break

        return "\n".join(lines)

    @staticmethod
    def _extract_symbols(code: str) -> List[FileSymbol]:
        symbols = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append(FileSymbol(name=node.name, kind="class", line=node.lineno))
                elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                    symbols.append(FileSymbol(name=node.name, kind="function", line=node.lineno))
        except SyntaxError:
            pass
        return symbols

    @staticmethod
    def _extract_imports(code: str) -> Set[str]:
        imports = set()
        for m in re.finditer(r"from\s+(\S+)\s+import|import\s+(\S+)", code):
            target = m.group(1) or m.group(2)
            if target and not target.startswith("."):
                imports.add(target.split(".")[0])
        return imports
