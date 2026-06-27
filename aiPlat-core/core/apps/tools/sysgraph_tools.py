"""
System Graph MCP Tools — expose code/capability graph queries to AI agents.

Registered in ToolRegistry, callable via sys_tool_call in ReAct loop.

Tools:
  sysgraph_context   → task → relevant code structure
  sysgraph_search    → symbol name → matching files  
  sysgraph_impact    → file path → blast radius (affected files)
  sysgraph_callers   → file path → files that depend on this
  sysgraph_node      → file path → full node detail (code + deps + symbols)
"""

from __future__ import annotations
import logging

from pathlib import Path
from typing import Any, Dict, List

from core.apps.tools.base import BaseTool, ToolConfig, ToolResult


# ============================================================
# Helpers
# ============================================================

def _get_graph():
    from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
    r = repo_root()
    roots = [(r / d).resolve() for d in default_roots()]
    nodes, edges, _ = build_graph(r, roots)
    return nodes, edges, r


def _read_source(repo_root: Path, filepath: str, max_lines: int = 80) -> str:
    try:
        full = repo_root / filepath
        if full.exists() and full.suffix == ".py":
            return "\n".join(full.read_text(encoding="utf-8", errors="ignore").split("\n")[:max_lines])
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return ""


# ============================================================
# Tool: sysgraph_context
# ============================================================

class SysGraphContextTool(BaseTool):
    """Build relevant code context for a task/question."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_context",
            description="Get relevant code structure for a task or question. Returns matching files, imports, and key symbols.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description or question about the codebase"},
                    "question": {"type": "string", "description": "Alternative: question about the codebase"},
                },
                "required": [],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        task = str(kwargs.get("task") or kwargs.get("question") or "").strip()
        if not task:
            return ToolResult(success=False, error="task or question parameter required")

        try:
            from core.harness.knowledge.code_graph import build_context, _ctx_to_prompt
            ctx = build_context(task)
            if ctx:
                return ToolResult(success=True, output=_ctx_to_prompt(ctx, max_chars=2000))
            return ToolResult(success=False, error="No matching context found")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_search
# ============================================================

class SysGraphSearchTool(BaseTool):
    """Search for files by name in the codebase."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_search",
            description="Search for files by name in the codebase. Returns matching paths with import degree info.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (file name or path fragment, min 2 chars)"},
                    "q": {"type": "string", "description": "Alias for query"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        query = str(kwargs.get("query") or kwargs.get("q") or "").strip()
        if not query or len(query) < 2:
            return ToolResult(success=False, error="query required (min 2 chars)")

        limit = int(kwargs.get("limit") or 10)
        try:
            nodes, _, _ = _get_graph()
            results = []
            q = query.lower()
            for nid, n in nodes.items():
                if q in nid.lower():
                    results.append(f"{nid} (in:{n.get('in',0)}, out:{len(n.get('out',[]))}, syms:{len(n.get('symbols',[]))})")
                    if len(results) >= limit:
                        break
            if results:
                return ToolResult(success=True, output="\n".join(results))
            return ToolResult(success=False, error=f"No files matching '{query}'")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_impact
# ============================================================

class SysGraphImpactTool(BaseTool):
    """Blast radius analysis for a file change."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_impact",
            description="Show which files would be affected by changes to a given file. Uses BFS over import graph.",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path to analyze blast radius for"},
                    "path": {"type": "string", "description": "Alias for file"},
                },
                "required": ["file"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        filepath = str(kwargs.get("file") or kwargs.get("path") or "").strip()
        if not filepath:
            return ToolResult(success=False, error="file parameter required")

        try:
            nodes, _, _ = _get_graph()
            from core.harness.knowledge.code_graph import blast
            radius = blast(nodes, filepath)
            if radius:
                result = f"Blast radius: {len(radius)} files affected by changes to {filepath}\n"
                result += "\n".join(f"  {b}" for b in radius[:20])
                if len(radius) > 20:
                    result += f"\n  ... and {len(radius) - 20} more"
                return ToolResult(success=True, output=result)
            return ToolResult(success=False, error=f"File not found or no blast data")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_callers
# ============================================================

class SysGraphCallersTool(BaseTool):
    """Find files that depend on a given file."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_callers",
            description="Find which files import or depend on a given file (reverse dependencies).",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Target file path"},
                    "path": {"type": "string", "description": "Alias for file"},
                    "limit": {"type": "integer", "description": "Max results (default 15)"},
                },
                "required": ["file"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        filepath = str(kwargs.get("file") or kwargs.get("path") or "").strip()
        limit = int(kwargs.get("limit") or 15)
        if not filepath:
            return ToolResult(success=False, error="file parameter required")

        try:
            nodes, _, _ = _get_graph()
            if filepath not in nodes:
                return ToolResult(success=False, error=f"File not found: {filepath}")

            callers = []
            for src, n in nodes.items():
                if filepath in n.get("out", []):
                    callers.append(src)
                    if len(callers) >= limit:
                        break

            if callers:
                result = f"Callers ({len(callers)}):\n"
                result += "\n".join(f"  {c}" for c in callers)
                return ToolResult(success=True, output=result)
            return ToolResult(success=True, output="No callers found")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_node
# ============================================================

class SysGraphNodeTool(BaseTool):
    """Full detail for a file node."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_node",
            description="Get full detail for a file: symbols (functions/classes), imports, dependents, and source code snippet.",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path to inspect"},
                    "path": {"type": "string", "description": "Alias for file"},
                },
                "required": ["file"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        filepath = str(kwargs.get("file") or kwargs.get("path") or "").strip()
        if not filepath:
            return ToolResult(success=False, error="file parameter required")

        try:
            nodes, _, repo_root = _get_graph()
            if filepath not in nodes:
                return ToolResult(success=False, error=f"File not found: {filepath}")

            n = nodes[filepath]
            symbols = n.get("symbols", [])
            in_d = int(n.get("in", 0))
            out_list = n.get("out", [])
            code = _read_source(repo_root, filepath, 60)

            result = f"=== {filepath} ===\n"
            result += f"Symbols ({len(symbols)}):\n"
            for name, kind, line in symbols[:25]:
                result += f"  {kind}: {name} (L{line})\n"
            result += f"\nImports ({len(out_list)}):\n"
            for d in out_list[:15]:
                result += f"  → {d}\n"
            result += f"\nDependents ({in_d}):\n"
            callers = [src for src, nd in nodes.items() if filepath in nd.get("out", [])]
            for c in callers[:10]:
                result += f"  ← {c}\n"
            if code:
                result += f"\n```python\n{code}\n```\n"

            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_affected_tests
# ============================================================

class SysGraphAffectedTestsTool(BaseTool):
    """Find test files affected by changed source files."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_affected_tests",
            description="Find which test files are affected by changes to the given source files. Used for running only relevant tests after code changes.",
            parameters={
                "type": "object",
                "properties": {
                    "files": {"type": "string", "description": "Comma-separated list of changed file paths"},
                },
                "required": ["files"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        files_str = str(kwargs.get("files") or "").strip()
        if not files_str:
            return ToolResult(success=False, error="files parameter required (comma-separated paths)")

        changed_files = [f.strip() for f in files_str.split(",") if f.strip()]
        try:
            nodes, _, _ = _get_graph()
            # Tests import source files, so check callers (incoming imports) of changed files
            affected: set = set()
            for f in changed_files:
                affected.add(f)
                # Find all files that import this file
                for src, n in nodes.items():
                    if f in n.get("out", []):
                        affected.add(src)

            # Filter for test files
            test_files = [f for f in affected if "/tests/" in f or "test_" in f or f.endswith("_test.py")]
            if test_files:
                result = f"Affected test files ({len(test_files)}):\n"
                result += "\n".join(f"  {t}" for t in test_files[:20])
                if len(test_files) > 20:
                    result += f"\n  ... and {len(test_files) - 20} more"
                return ToolResult(success=True, output=result)
            return ToolResult(success=True, output="No affected test files found")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_review
# ============================================================

class SysGraphReviewTool(BaseTool):
    """Build minimal review context for a set of changed files."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_review",
            description="Build minimal code review context for changed files. Returns: callers, callees, affected tests, and code snippets for each changed file.",
            parameters={
                "type": "object",
                "properties": {
                    "files": {"type": "string", "description": "Comma-separated list of changed file paths to review"},
                },
                "required": ["files"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        files_str = str(kwargs.get("files") or "").strip()
        if not files_str:
            return ToolResult(success=False, error="files parameter required")

        changed_files = [f.strip() for f in files_str.split(",") if f.strip()][:10]  # max 10 files
        try:
            nodes, edges, repo_root = _get_graph()

            # Tests import source files, so check callers of changed files
            affected = set(changed_files)
            for f in changed_files:
                for src, n in nodes.items():
                    if f in n.get("out", []):
                        affected.add(src)
            test_files = [f for f in affected if "/tests/" in f or "test_" in f or f.endswith("_test.py")]

            result = "=== Code Review Context ===\n\n"
            for fp in changed_files:
                if fp not in nodes:
                    result += f"## {fp}\n  (not indexed)\n\n"
                    continue
                n = nodes[fp]
                in_d = int(n.get("in", 0))
                out_list = n.get("out", [])
                symbols = n.get("symbols", [])[:15]
                callers = [src for src, nd in nodes.items() if fp in nd.get("out", [])][:10]
                code = _read_source(repo_root, fp, 40)

                result += f"## {fp} (in:{in_d}, out:{len(out_list)}, syms:{len(n.get('symbols',[]))})\n"
                if symbols:
                    result += f"  Key symbols: {', '.join(s[0] for s in symbols[:8])}\n"
                if callers:
                    result += f"  Callers: {', '.join(c.split('/')[-1] for c in callers[:5])}\n"
                if out_list:
                    result += f"  Imports: {', '.join(d.split('/')[-1] for d in out_list[:5])}\n"
                if code:
                    result += f"  ```\n{code[:400]}\n  ```\n"
                result += "\n"

            if test_files:
                result += f"## Affected Tests ({len(test_files)}):\n"
                result += "\n".join(f"  {t}" for t in test_files[:15])
                result += "\n"

            return ToolResult(success=True, output=result[:8000])  # cap at 8k chars
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_deps
# ============================================================

class SysGraphDepsTool(BaseTool):
    """Full transitive dependency tree for a file: both imports and dependents, with configurable depth."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_deps",
            description="Return the full dependency tree for a file: what it imports (with transitive closure) and what depends on it (reverse callers). Supports depth limit and direction filtering.",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path (relative to repo root) to analyze"},
                    "path": {"type": "string", "description": "Alias for file"},
                    "depth": {"type": "integer", "description": "Max depth for transitive traversal (default 3)"},
                    "direction": {"type": "string", "description": "both | imports | dependents (default both)"},
                },
                "required": ["file"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        path = str(kwargs.get("file") or kwargs.get("path") or "").strip()
        if not path:
            return ToolResult(success=False, error="file parameter required")
        depth = int(kwargs.get("depth", 3))
        direction = str(kwargs.get("direction", "both"))
        try:
            nodes, edges, repo_root = _get_graph()
            if path not in nodes:
                return ToolResult(success=False, error=f"File not found in graph: {path}")

            result = f"=== Dependency tree for: {path} ===\nDepth: {depth}, Direction: {direction}\n\n"

            if direction in ("both", "imports"):
                result += "📦 Imports (what this file depends on):\n"
                result += _bfs_tree(nodes, path, "out", depth, "")
                result += "\n"

            if direction in ("both", "dependents"):
                callers = [src for src, n in nodes.items() if path in n.get("out", [])]
                result += "📦 Dependents (what depends on this file):\n"
                if callers:
                    result += _reverse_tree(nodes, path, callers, depth, "")
                else:
                    result += "  (no direct callers)\n"

            cross_calls = [e for e in edges
                           if e.get("kind") == "calls" and e.get("cross")
                           and (e["from"] == path or e["to"] == path)][:15]
            if cross_calls:
                result += "\n🔗 Cross-file calls:\n"
                for e in cross_calls:
                    result += f"  {e['from'].split('/')[-1]} → {e['to'].split('/')[-1]} ({e.get('label', '?')})\n"

            return ToolResult(success=True, output=result[:8000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


def _bfs_tree(nodes, start, key, max_depth, prefix):
    """BFS forward traversal, formatted as indented tree."""
    lines = []
    visited = {start}
    queue = [(start, 0, prefix)]
    while queue:
        current, d, indent = queue.pop(0)
        if d >= max_depth:
            continue
        targets = nodes.get(current, {}).get(key, [])
        for i, t in enumerate(targets):
            if t in visited:
                continue
            visited.add(t)
            is_last = (i == len(targets) - 1)
            branch = "└── " if is_last else "├── "
            lines.append(f"{indent}{branch}{t}")
            next_indent = indent + ("    " if is_last else "│   ")
            queue.append((t, d + 1, next_indent))
    return "\n".join(lines) if lines else "  (none)\n"


def _reverse_tree(nodes, start, callers, max_depth, prefix):
    """Build tree of callers at depth 1, then recurse."""
    lines = []
    visited = {start}
    queue = [(start, 0, prefix, callers)]
    while queue:
        current, d, indent, deps = queue.pop(0)
        if d >= max_depth:
            continue
        for i, c in enumerate(deps):
            if c in visited:
                continue
            visited.add(c)
            is_last = (i == len(deps) - 1)
            branch = "└── " if is_last else "├── "
            lines.append(f"{indent}{branch}{c}")
            next_indent = indent + ("    " if is_last else "│   ")
            sub_callers = [src for src, n in nodes.items() if c in n.get("out", [])]
            if sub_callers:
                queue.append((c, d + 1, next_indent, sub_callers))
    return "\n".join(lines) if lines else "  (none)\n"


# ============================================================
# Tool: sysgraph_diff
# ============================================================

class SysGraphDiffTool(BaseTool):
    """Compare dependency profiles of two files: shared vs unique imports, callers, and cross-file calls."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_diff",
            description="Compare the dependency profiles of two files. Shows shared vs unique imports, shared callers, cross-file call overlap, and symbol overlap.",
            parameters={
                "type": "object",
                "properties": {
                    "file_a": {"type": "string", "description": "First file path (relative to repo root)"},
                    "file_b": {"type": "string", "description": "Second file path (relative to repo root)"},
                    "a": {"type": "string", "description": "Alias for file_a"},
                    "b": {"type": "string", "description": "Alias for file_b"},
                },
                "required": ["file_a", "file_b"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        a = str(kwargs.get("file_a") or kwargs.get("a") or "").strip()
        b = str(kwargs.get("file_b") or kwargs.get("b") or "").strip()
        if not a or not b:
            return ToolResult(success=False, error="file_a and file_b required")
        try:
            nodes, edges, repo_root = _get_graph()
            if a not in nodes:
                return ToolResult(success=False, error=f"File A not found: {a}")
            if b not in nodes:
                return ToolResult(success=False, error=f"File B not found: {b}")

            ia = set(nodes[a].get("out", []))
            ib = set(nodes[b].get("out", []))
            ca = {src for src, n in nodes.items() if a in n.get("out", [])}
            cb = {src for src, n in nodes.items() if b in n.get("out", [])}

            sa = _short_path(a)
            sb = _short_path(b)

            result = f"=== Dependency Profile Diff ===\n"
            result += f"A: {sa} (imports:{len(ia)}, callers:{len(ca)})\n"
            result += f"B: {sb} (imports:{len(ib)}, callers:{len(cb)})\n\n"

            shared_imports = ia & ib
            if shared_imports:
                result += f"🔄 Shared imports ({len(shared_imports)}):\n"
                result += "\n".join(f"  → {_short_path(s)}" for s in sorted(shared_imports)[:10])
                result += "\n\n"

            a_only = ia - ib
            if a_only:
                result += f"📁 Unique to A ({len(a_only)}):\n"
                result += "\n".join(f"  → {_short_path(s)}" for s in sorted(a_only)[:8])
                result += "\n\n"

            b_only = ib - ia
            if b_only:
                result += f"📁 Unique to B ({len(b_only)}):\n"
                result += "\n".join(f"  → {_short_path(s)}" for s in sorted(b_only)[:8])
                result += "\n\n"

            shared_callers = ca & cb
            if shared_callers:
                result += f"🔄 Shared callers ({len(shared_callers)}):\n"
                result += "\n".join(f"  ← {_short_path(s)}" for s in sorted(shared_callers)[:8])
                result += "\n\n"

            result += f"📞 Cross-file calls:\n"
            a_to_b = [e for e in edges if e.get("kind") == "calls" and e.get("cross")
                      and e["from"] == a and e["to"] == b]
            b_to_a = [e for e in edges if e.get("kind") == "calls" and e.get("cross")
                      and e["from"] == b and e["to"] == a]
            result += f"  A → B: {'yes (' + str(len(a_to_b)) + ')' if a_to_b else 'no'}\n"
            result += f"  B → A: {'yes (' + str(len(b_to_a)) + ')' if b_to_a else 'no'}\n"

            syms_a = set(s[0] for s in nodes[a].get("symbols", []))
            syms_b = set(s[0] for s in nodes[b].get("symbols", []))
            shared_syms = syms_a & syms_b
            if shared_syms:
                result += f"\n📊 Symbol overlap: {len(shared_syms)} shared symbols\n"
                result += f"  {', '.join(sorted(shared_syms)[:12])}\n"

            return ToolResult(success=True, output=result[:8000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


def _short_path(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return "/".join(parts[-2:]) if len(parts) > 2 else path


# ============================================================
# Tool: sysgraph_related
# ============================================================

class SysGraphRelatedTool(BaseTool):
    """Find files related to a given file: shared imports, same directory, symbol overlap."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_related",
            description="Find code files related to a given file by shared imports, same directory siblings, and symbol name overlap. Useful for discovering which files work together.",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path (relative to repo root) to find related files for"},
                    "path": {"type": "string", "description": "Alias for file"},
                    "limit": {"type": "integer", "description": "Max related files to return (default 10)"},
                },
                "required": ["file"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        path = str(kwargs.get("file") or kwargs.get("path") or "").strip()
        if not path:
            return ToolResult(success=False, error="file parameter required")
        limit = int(kwargs.get("limit", 10))
        try:
            nodes, edges, repo_root = _get_graph()
            if path not in nodes:
                return ToolResult(success=False, error=f"File not found: {path}")

            n = nodes[path]
            my_imports = set(n.get("out", []))
            my_dir = "/".join(path.split("/")[:-1])
            my_symbols = set(s[0] for s in n.get("symbols", []))

            scored = []
            for other_path, other_n in nodes.items():
                if other_path == path:
                    continue
                score = 0
                reasons = []

                # Shared imports (Jaccard similarity)
                other_imports = set(other_n.get("out", []))
                shared_imps = my_imports & other_imports
                if shared_imps:
                    score += len(shared_imps) * 3
                    reasons.append(f"shared-imports({len(shared_imps)})")

                # Same directory
                other_dir = "/".join(other_path.split("/")[:-1])
                if other_dir == my_dir:
                    score += 2
                    reasons.append("same-dir")

                # Symbol overlap
                other_symbols = set(s[0] for s in other_n.get("symbols", []))
                shared_syms = my_symbols & other_symbols
                if shared_syms:
                    score += len(shared_syms) * 1
                    reasons.append(f"shared-symbols({len(shared_syms)})")

                # Import chain: this file imports X, other also imports X
                if score > 0:
                    scored.append((score, other_path, reasons))

            scored.sort(key=lambda x: -x[0])
            top = scored[:limit]

            result = f"=== Files related to {_short_path(path)} ===\n\n"
            for score, rel_path, reasons in top:
                result += f"  {_short_path(rel_path)} (score:{score} [{', '.join(reasons)}])\n"

            if not top:
                result += "  No strongly related files found.\n"

            return ToolResult(success=True, output=result[:8000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_stats
# ============================================================

class SysGraphStatsTool(BaseTool):
    """Global codebase statistics: files, edges, symbols, top modules, health."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_stats",
            description="Return global codebase statistics: total files/edges/symbols, layer breakdown, top imported files, top dependent files, and health score. Use this to get a birds-eye view of the codebase.",
            parameters={
                "type": "object",
                "properties": {},
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        try:
            from core.harness.knowledge.code_graph import (
                build_graph, default_roots, repo_root, health_score, count_cycles
            )
            r = repo_root()
            roots = [(r / d).resolve() for d in default_roots()]
            nodes, edges, _ = build_graph(r, roots)

            total_files = len(nodes)
            total_edges = len(edges)
            import_edges = sum(1 for e in edges if e.get("kind", "import") == "import")
            call_edges = sum(1 for e in edges if e.get("kind") == "calls")
            cross_edges = sum(1 for e in edges if e.get("cross"))
            total_symbols = sum(len(n.get("symbols", [])) for n in nodes.values())

            cycles = count_cycles(nodes)
            health = health_score(nodes=nodes, edges=edges, issues=[], cycles_back_edges=cycles)

            # Layer breakdown
            layers = {"infra": 0, "core": 0, "platform": 0, "app": 0, "management": 0}
            for p in nodes:
                top = p.split("/")[0] if "/" in p else p
                if top.startswith("aiPlat-"):
                    layer = top.replace("aiPlat-", "")
                    layers[layer] = layers.get(layer, 0) + 1

            # Top files by in-degree (most imported)
            top_in = sorted(nodes.items(), key=lambda x: x[1].get("in", 0), reverse=True)[:8]
            # Top files by out-degree (most dependencies)
            top_out = sorted(nodes.items(), key=lambda x: len(x[1].get("out", [])), reverse=True)[:8]

            result = f"=== Codebase Statistics ===\n"
            result += f"Files: {total_files}  |  Edges: {total_edges} (import:{import_edges} call:{call_edges} cross:{cross_edges})\n"
            result += f"Symbols: {total_symbols}  |  Cycles: {cycles}\n"
            result += f"Health: {health.get('score', '?')}/100 ({health.get('grade', '?')})\n\n"

            result += "--- Layer Breakdown ---\n"
            for layer, count in sorted(layers.items(), key=lambda x: -x[1]):
                if count:
                    result += f"  {layer}: {count} files\n"
            result += "\n"

            result += "--- Top Imported (highest in-degree) ---\n"
            for p, n in top_in:
                result += f"  {_short_path(p)} (in:{n.get('in',0)})\n"
            result += "\n"

            result += "--- Top Dependents (highest out-degree) ---\n"
            for p, n in top_out:
                result += f"  {_short_path(p)} (out:{len(n.get('out',[]))})\n"

            return ToolResult(success=True, output=result[:8000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_tests
# ============================================================

class SysGraphTestsTool(BaseTool):
    """Find test files for source files, identify untested files, and show test coverage gaps."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_tests",
            description="Find test files related to source files. Given a file, finds its test file(s). Given no file, lists untested source files (files with no corresponding test in same layer).",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Source file path to find test for"},
                    "path": {"type": "string", "description": "Alias for file"},
                    "untested": {"type": "boolean", "description": "List untested source files instead (default true when no file given)"},
                    "limit": {"type": "integer", "description": "Max results (default 15)"},
                },
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        path = str(kwargs.get("file") or kwargs.get("path") or "").strip()
        untested = bool(kwargs.get("untested", not path))
        limit = int(kwargs.get("limit", 15))
        try:
            nodes, edges, repo_root = _get_graph()
            test_files = set()
            source_files = set()
            for p, n in nodes.items():
                parts = p.replace("\\", "/").split("/")
                if any(x in parts for x in ("tests", "test", "__pycache__")):
                    if p.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                        test_files.add(p)
                elif p.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                    source_files.add(p)

            if path:
                return await self._find_test_for(path, nodes, test_files, limit)
            elif untested:
                return self._list_untested(source_files, test_files, nodes, limit)
            else:
                return ToolResult(success=True, output="Specify a file path or set untested=true")

        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _find_test_for(self, path, nodes, test_files, limit):
        result = f"=== Test files for: {_short_path(path)} ===\n\n"
        basename = path.split("/")[-1].rsplit(".", 1)[0]
        matches = set()
        for t in test_files:
            t_base = t.split("/")[-1].rsplit(".", 1)[0]
            if basename in t_base or t_base in basename:
                matches.add(t)

        if matches:
            result += f"📝 Matching test files ({len(matches)}):\n"
            for m in sorted(matches)[:limit]:
                result += f"  - {_short_path(m)}\n"
        else:
            src_dir = "/".join(path.split("/")[:-1])
            dir_matches = [t for t in test_files if src_dir and "/".join(t.split("/")[:-1]).endswith(src_dir)]
            if dir_matches:
                result += f"📁 Same-directory test files ({len(dir_matches)}):\n"
                for m in sorted(dir_matches)[:limit]:
                    result += f"  - {_short_path(m)}\n"
            else:
                result += "  No test files found.\n"

        imports_to_tests = [i for i in nodes.get(path, {}).get("out", []) if i in test_files]
        if imports_to_tests:
            result += f"\n🔗 Imports from test files ({len(imports_to_tests)}):\n"
            for i in imports_to_tests[:5]:
                result += f"  → {_short_path(i)}\n"

        return ToolResult(success=True, output=result[:8000])

    def _list_untested(self, source_files, test_files, nodes, limit):
        untested = []
        for src in source_files:
            basename = src.split("/")[-1].rsplit(".", 1)[0]
            has_test = False
            for t in test_files:
                t_base = t.split("/")[-1].rsplit(".", 1)[0]
                if basename in t_base or t_base in basename:
                    has_test = True
                    break
            if not has_test:
                in_deg = nodes.get(src, {}).get("in", 0)
                untested.append((in_deg, src))

        untested.sort(key=lambda x: -x[0])

        total = len(source_files)
        tested = total - len(untested)
        pct = round(tested / max(total, 1) * 100, 1)

        result = f"=== Test Coverage Gaps ===\n"
        result += f"Source files: {total} | Tested: {tested} ({pct}%) | Untested: {len(untested)}\n\n"
        result += f"Top {limit} untested files (by in-degree):\n"
        for in_deg, src in untested[:limit]:
            result += f"  {_short_path(src)} (in:{in_deg})\n"

        return ToolResult(success=True, output=result[:8000])


# ============================================================
# Tool: sysgraph_hotspots
# ============================================================

class SysGraphHotspotsTool(BaseTool):
    """Identify code hotspots: most-depended-on files, most-complex files, most issues."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_hotspots",
            description="Identify code hotspots: top files by in-degree (most depended on), out-degree (most dependencies), issues, and symbol count. Useful for finding high-risk modules that need attention.",
            parameters={
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "description": "indegree | outdegree | issues | symbols (default indegree)"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                    "layer": {"type": "string", "description": "Filter by layer: core, infra, platform, app, management"},
                },
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        metric = str(kwargs.get("metric", "indegree")).strip()
        limit = int(kwargs.get("limit", 10))
        layer_filter = str(kwargs.get("layer", "")).strip()
        try:
            nodes, edges, repo_root = _get_graph()

            if metric in ("indegree", "in"):
                scored = [(n.get("in", 0), p) for p, n in nodes.items()]
            elif metric in ("outdegree", "out"):
                scored = [(len(n.get("out", [])), p) for p, n in nodes.items()]
            elif metric == "issues":
                scored = [(n.get("issue_count", 0), p) for p, n in nodes.items()]
            elif metric == "symbols":
                scored = [(len(n.get("symbols", [])), p) for p, n in nodes.items()]
            else:
                return ToolResult(success=False, error=f"Unknown metric: {metric}. Use indegree, outdegree, issues, or symbols")

            if layer_filter:
                scored = [(s, p) for s, p in scored
                          if p.replace("\\", "/").startswith(f"aiPlat-{layer_filter}/")]

            scored.sort(key=lambda x: -x[0])
            top = scored[:limit]

            labels = {"indegree": "Most Imported", "outdegree": "Most Dependencies",
                      "issues": "Most Issues", "symbols": "Most Symbols"}
            label = labels.get(metric, metric)
            if metric in ("indegree", "in"): label = "Most Imported"
            elif metric in ("outdegree", "out"): label = "Most Dependencies"

            result = f"=== Code Hotspots: {label} ===\n"
            if layer_filter:
                result += f"Layer: aiPlat-{layer_filter}\n"
            result += f"\n"
            for score, p in top:
                result += f"  {_short_path(p)} ({score})\n"

            return ToolResult(success=True, output=result[:8000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_find
# ============================================================

class SysGraphFindTool(BaseTool):
    """Find where a function, class, or symbol is defined across the codebase."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_find",
            description="Find where a function, class, or symbol is defined across the entire codebase. Given a name, returns all files that define it with kind (function/class/async_function) and line number.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Function, class, or symbol name to find"},
                    "query": {"type": "string", "description": "Alias for name"},
                    "kind": {"type": "string", "description": "Filter by kind: function, class, async_function, or all (default)"},
                    "limit": {"type": "integer", "description": "Max results (default 20)"},
                },
                "required": ["name"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        name = str(kwargs.get("name") or kwargs.get("query") or "").strip()
        if not name:
            return ToolResult(success=False, error="name parameter required")
        kind_filter = str(kwargs.get("kind", "")).strip()
        limit = int(kwargs.get("limit", 20))
        try:
            nodes, edges, repo_root = _get_graph()
            found = []
            for path, node in nodes.items():
                for sym_name, sym_kind, line in node.get("symbols", []):
                    if sym_name == name:
                        if kind_filter and sym_kind != kind_filter:
                            continue
                        found.append((path, sym_kind, line))

            result = f"=== Definition lookup: {name} ===\n"
            if kind_filter:
                result += f"Kind filter: {kind_filter}\n"
            result += f"Found in {len(found)} file(s)\n\n"

            for path, kind, line in found[:limit]:
                snippet = ""
                try:
                    code_path = repo_root / path
                    if code_path.exists():
                        lines = code_path.read_text(encoding="utf-8").split("\n")
                        s = max(0, line - 3)
                        e = min(len(lines), line + 2)
                        snips = []
                        for i in range(s, e):
                            marker = ">" if i == line - 1 else " "
                            snips.append(f"{marker} {lines[i].strip()[:120]}")
                        snippet = "\n    ".join(snips)
                except Exception:
                    snippet = f"line {line}"
                result += f"  {_short_path(path)}:{line} [{kind}]\n"
                if snippet:
                    result += f"    {snippet}\n"

            return ToolResult(success=True, output=result[:8000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sysgraph_churn
# ============================================================

class SysGraphChurnTool(BaseTool):
    """Show recently changed files via git log, with change frequency."""

    def __init__(self):
        config = ToolConfig(
            name="sysgraph_churn",
            description="Show recently changed files via git log. Returns files sorted by recent modification, with change count in the last N commits. Useful for finding actively maintained or unstable code.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max files to return (default 15)"},
                    "commits": {"type": "integer", "description": "Number of commits to analyze (default 30)"},
                },
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        limit = int(kwargs.get("limit", 15))
        num_commits = int(kwargs.get("commits", 30))
        try:
            import subprocess
            from collections import Counter
            nodes, edges, repo_root = _get_graph()

            result = "=== Recent Changes (git churn) ===\n\n"
            try:
                output = subprocess.run(
                    ["git", "log", f"-{num_commits}", "--name-only", "--pretty=format:", "--diff-filter=AM"],
                    capture_output=True, text=True, timeout=10, cwd=str(repo_root)
                )
                if output.returncode == 0 and output.stdout.strip():
                    churn = Counter(
                        f.strip() for f in output.stdout.strip().split("\n")
                        if f.strip() and f.strip() in nodes
                    )
                    result += f"Files changed in last {num_commits} commits:\n"
                    for f, count in churn.most_common(limit):
                        result += f"  {_short_path(f)} ({count} changes)\n"
                else:
                    result += "  No recent changes detected.\n"
            except Exception:
                result += "  git log unavailable.\n"

            import time as _t
            recent = [(n.get("_mtime", 0), p) for p, n in nodes.items() if n.get("_mtime", 0) > 0]
            if recent:
                recent.sort(key=lambda x: -x[0])
                result += f"\n--- Recently Modified (mtime) ---\n"
                for mtime, p in recent[:limit]:
                    ago = int(_t.time() - mtime)
                    if ago > 86400:
                        val, unit = ago // 86400, "d"
                    elif ago > 3600:
                        val, unit = ago // 3600, "h"
                    elif ago > 60:
                        val, unit = ago // 60, "m"
                    else:
                        val, unit = ago, "s"
                    result += f"  {_short_path(p)} ({val}{unit} ago)\n"

            return ToolResult(success=True, output=result[:8000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ============================================================
# Tool: sys_lsp_fix
# ============================================================

class SysLspFixTool(BaseTool):
    """Agent self-repair: read context around an LSP diagnostic error, enabling the Agent to generate and apply fixes via sys_file_edit. Can also re-verify after fix."""

    def __init__(self):
        config = ToolConfig(
            name="sys_lsp_fix",
            description="Prepare context for fixing a pyright LSP diagnostic error. Given a file path and line number, returns the surrounding code so the Agent can generate the correct fix. After applying fixes, call with verify=true to re-run pyright on that file.",
            parameters={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "File path with the error"},
                    "path": {"type": "string", "description": "Alias for file"},
                    "line": {"type": "integer", "description": "Line number of the error"},
                    "rule": {"type": "string", "description": "Pyright rule code (e.g., reportArgumentType)"},
                    "verify": {"type": "boolean", "description": "Re-run pyright after fix to verify (default: false)"},
                },
                "required": ["file", "line"],
            },
        )
        super().__init__(config)

    async def execute(self, **kwargs) -> ToolResult:
        filepath = str(kwargs.get("file") or kwargs.get("path") or "").strip()
        line = int(kwargs.get("line", 0))
        rule = str(kwargs.get("rule", ""))
        verify = bool(kwargs.get("verify", False))
        if not filepath or not line:
            return ToolResult(success=False, error="file and line required")
        try:
            import subprocess, json, os
            from pathlib import Path

            repo_root = os.getcwd()
            full_path = Path(repo_root) / filepath
            if not full_path.exists():
                full_path = Path(filepath)
                if not full_path.exists():
                    return ToolResult(success=False, error=f"File not found: {filepath}")

            if verify:
                cmd = ["npx", "pyright", "--outputjson", str(full_path)]
                config = Path(repo_root) / "aiPlat-core" / "pyrightconfig.json"
                if config.exists():
                    cmd = ["npx", "pyright", "--outputjson", "--project", str(config), str(full_path)]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=repo_root)
                try:
                    data = json.loads(r.stdout)
                    diags = data.get("generalDiagnostics", [])
                    remaining = len(diags)
                    if remaining == 0:
                        return ToolResult(success=True,
                            output=f"✅ pyright re-check PASSED: {filepath}\n  No remaining issues.")
                    errors = sum(1 for d in diags if d.get("severity") == "error")
                    return ToolResult(success=True,
                        output=f"⚠️ pyright re-check: {filepath}\n  {remaining} remaining ({errors} errors, {remaining - errors} warnings)")
                except json.JSONDecodeError:
                    return ToolResult(success=True,
                        output=f"pyright re-checked: {filepath}\n  (parse error in output)")

            lines_text = full_path.read_text(encoding="utf-8").split("\n")
            start = max(0, line - 5)
            end = min(len(lines_text), line + 4)
            ctx = []
            for i in range(start, end):
                marker = ">>>" if i == line - 1 else "   "
                ctx.append(f"{marker} {i+1}: {lines_text[i][:120]}")

            result = f"=== LSP Fix Context ===\n"
            result += f"File: {filepath}\nError line: {line}\n"
            if rule:
                result += f"Rule: {rule}\n"
            result += f"\n```python\n{chr(10).join(ctx)}\n```\n"
            result += f"\nInstructions: 1) sys_file_read to see full file, 2) sys_file_edit to apply fix, 3) sys_lsp_fix(verify=true) to re-check.\n"

            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
