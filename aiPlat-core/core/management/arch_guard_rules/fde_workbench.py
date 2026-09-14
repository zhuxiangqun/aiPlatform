"""FDE Workbench Contract — architecture guard checks (§98).

Maps to docs/contracts/FDE_WORKBENCH_CONTRACT.md.
Uses existing ArchRule discovery (not a parallel architecture_guard package).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List

from core.management.arch_guard_base import ArchIssue, ArchRule

# Literal customer / tracking domains forbidden as behavior forks in harness.
_FORBIDDEN_DOMAIN_RE = re.compile(
    r"^(fde-delivery|lock-service|supply-chain|media-.+)$"
)

_HARNESS_EXCLUDE_PARTS = (
    "/tests/",
    "test_",
    "domain_router.py",
    "ontology_loader.py",
    "builtin_handlers.py",
    "builtin_actions.py",
    "ontology_branch.py",
    "ontology_validator.py",
    "prompt_loader.py",
    "action_audit_validate.py",
    "# noqa: domain-literal",
)


class FdeDomainLiteralsAstCheck(ArchRule):
    """§98: harness 中禁止字面量客户域名（允许常量赋值 / DomainRouter 调用参数）。"""

    code = "fde_domain_literals"
    level = "error"  # Phase 5: D2 closed — behavior forks cleared; CI blocks new literals
    section_number = "§98"
    section_name = "FDE Workbench Contract"

    def check(self, repo_root: Path) -> List[ArchIssue]:
        harness = repo_root / "aiPlat-core" / "core" / "harness"
        if not harness.is_dir():
            return []
        hits: List[str] = []
        for py_file in harness.rglob("*.py"):
            rel = str(py_file.relative_to(repo_root))
            if any(p in rel for p in _HARNESS_EXCLUDE_PARTS):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "# noqa: domain-literal" in source:
                continue
            try:
                tree = ast.parse(source, filename=rel)
            except SyntaxError:
                continue
            for lit, lineno in _forbidden_domain_literals(tree):
                hits.append(f"{rel}:{lineno}: {lit}")
                if len(hits) >= 80:
                    break
            if len(hits) >= 80:
                break
        if not hits:
            return []
        return [
            ArchIssue(
                level=self.level,
                code=self.code,
                message=(
                    "hardcoded domain literal in harness — use DomainRouter "
                    "(see FDE_WORKBENCH_CONTRACT.md §3)"
                ),
                files=hits,
                count=len(hits),
            )
        ]


def _forbidden_domain_literals(tree: ast.AST) -> List[tuple]:
    """Return (literal, lineno) for forbidden domain strings not in allow_if."""
    out: List[tuple] = []
    parent_map: dict = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if not _FORBIDDEN_DOMAIN_RE.match(node.value):
            continue
        parent = parent_map.get(node)
        if _is_allowed_domain_literal(node, parent, parent_map):
            continue
        out.append((node.value, getattr(node, "lineno", 0)))
    return out


def _is_allowed_domain_literal(node: ast.Constant, parent: ast.AST | None, parent_map: dict) -> bool:
    if parent is None:
        return False
    # Constant assignment: PLATFORM_TRACKING_DOMAIN = "fde-delivery"
    if isinstance(parent, (ast.Assign, ast.AnnAssign)):
        return True
    # frozenset({"fde-delivery", ...}) / set([...])
    if isinstance(parent, (ast.Set, ast.List, ast.Tuple)):
        gp = parent_map.get(parent)
        if isinstance(gp, ast.Call):
            fname = ""
            if isinstance(gp.func, ast.Name):
                fname = gp.func.id
            elif isinstance(gp.func, ast.Attribute):
                fname = gp.func.attr
            if fname in {"frozenset", "set", "list", "tuple"}:
                return True
        if isinstance(gp, (ast.Assign, ast.AnnAssign)):
            return True
    # Call arg: DomainRouter.resolve("lock-service") / GraphIndex.load(...)
    if isinstance(parent, ast.Call):
        func = parent.func
        name = ""
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name in {"resolve", "resolve_domain", "load", "list_domains", "get_domain", "frozenset", "set"}:
            return True
    # Nested: Compare right side domain_id == "lock-service" → NOT allowed
    if isinstance(parent, ast.Compare):
        return False
    return False


class FdeWorkbenchForbiddenFrontendCheck(ArchRule):
    """§98: FDE 工作台前端禁止 IDE 类依赖。"""

    code = "fde_workbench_forbidden_components"
    level = "error"
    section_number = "§98"
    section_name = "FDE Workbench Contract"

    _IMPORT_RE = re.compile(
        r"""from\s+['"](?:monaco-editor|@monaco-editor/react|codemirror|@codemirror/|ace-builds|react-ace|xterm|xterm-for-react|react-file-tree)['"]"""
        r"""|import\s+.*from\s+['"](?:monaco-editor|@monaco-editor/react|codemirror|ace-builds|react-ace|xterm)['"]"""
    )
    _COMPONENT_RE = re.compile(r"<(?:Editor|CodeEditor|FileTree|Terminal)\b")

    def check(self, repo_root: Path) -> List[ArchIssue]:
        roots = [
            repo_root / "aiPlat-management" / "frontend" / "src" / "pages" / "Diagnostics",
        ]
        hits: List[str] = []
        for root in roots:
            if not root.is_dir():
                continue
            for path in list(root.rglob("*.tsx")) + list(root.rglob("*.ts")):
                if ".test." in path.name:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                rel = str(path.relative_to(repo_root))
                for i, line in enumerate(text.splitlines(), 1):
                    if self._IMPORT_RE.search(line) or self._COMPONENT_RE.search(line):
                        hits.append(f"{rel}:{i}: {line.strip()[:100]}")
        if not hits:
            return []
        return [
            ArchIssue(
                level=self.level,
                code=self.code,
                message=(
                    "FDE workbench must not import IDE components "
                    "(FDE_WORKBENCH_CONTRACT.md §4)"
                ),
                files=hits,
                count=len(hits),
            )
        ]
