"""
Capability Health — extensible rules engine for capability graph analysis.

Each rule receives a shared CapabilityGraphContext (adjacency pre-built once).
Adding a new check: create a CapRule subclass in this file (auto-discovered).

Architecture:
  - CapContext: shared adjacency + stats (built once from graph)
  - CapRule: check(ctx) → List[CapIssue] + penalty_formula(ctx, issues) → float
  - CapHealthRegistry: builds context, runs all rules, computes score
"""

from __future__ import annotations
import logging

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


# ============================================================
# Data classes
# ============================================================

@dataclass
class CapIssue:
    type: str
    label: str
    detail: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapContext:
    """Pre-built adjacency and stats shared by all rules."""
    nodes: Dict[str, Dict[str, Any]]
    edges: List[Dict[str, Any]]
    in_degree: Dict[str, int]
    out_degree: Dict[str, int]
    neighbors: Dict[str, List[str]]
    total_degree: Dict[str, int]
    by_type: Dict[str, int]


@dataclass
class CapHealthReport:
    score: float
    grade: str
    signals: Dict[str, Any]
    issues: Dict[str, List]
    top_hubs: List[Dict[str, Any]]
    top_blast: List[Dict[str, Any]]
    by_type: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "score": self.score,
            "grade": self.grade,
            "signals": self.signals,
            "issues": self.issues,
            "top_hubs": self.top_hubs,
            "top_blast": self.top_blast,
            "by_type": self.by_type,
        }
        # Flatten dict-typed issues for API compatibility
        for k, v in self.issues.items():
            result["issues"][k] = v
        return result


# ============================================================
# Rule base
# ============================================================

class CapRule:
    """Base class for capability health rules."""

    code: str = ""
    issue_key: str = ""  # key in report.issues dict
    description: str = ""

    def check(self, ctx: CapContext) -> List[CapIssue]:
        raise NotImplementedError

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        """Return penalty to deduct from health score."""
        return 0.0

    def bonus(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        """Return bonus to add to health score."""
        return 0.0


# ============================================================
# Rules
# ============================================================

class UnusedSkillCheck(CapRule):
    code = "unused_skills"
    issue_key = "unused_skills"
    description = "Unused skills (0 in-degree)"
    
    # All engine skills are internally available via harness sys_skill_call()
    # They don't need AGENT.md binding — only workspace skills do.
    _ENGINE_INTERNAL = {
        "api_calling", "browser_automation", "chitchat", "code_generation",
        "code_review", "data_analysis", "doc_query", "e2e_test",
        "eval_code_generator", "file_operations", "information_search",
        "knowledge_editor", "knowledge_ingest", "knowledge_query",
        "knowledge_retrieval", "multi_doc_query", "root_cause_analysis",
        "site_tester", "skill_apply_engine_skill_md_patch", "skill_eval_quality",
        "skill_eval_trigger", "summarization", "task_decomposition",
        "task_planning", "test_case_generation", "text_generation",
        "translation", "wiki_lint", "wiki_query",
    }

    # Workspace persona skills are injected via agent system prompt (not sys_skill_call)
    # They won't appear in AGENT.md required_skills but ARE used at runtime.
    _WORKSPACE_PERSONA = {
        "ponytail-lazy", "security-auditor", "test-engineer", "web-perf-auditor",
    }

    # Workspace utility skills are available system-wide and don't need agent binding.
    # They function as prompt-only templates (execution_type=prompt) called on-demand.
    _WORKSPACE_UTILITY = {
        "capability_scout", "code", "component_design", "data_model_design",
        "http_request", "refactor_flat_to_layered", "summarize",
        "tech_selection", "webhook_trigger",
    }

    # Engine system skills registered for global availability.
    _ENGINE_SYSTEM = {
        "code-hygiene",
    }

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        for nid, n in ctx.nodes.items():
            if n["type"] in ("skill", "workspace_skill") and ctx.in_degree.get(nid, 0) == 0:
                if n["label"] in self._ENGINE_INTERNAL or n["label"] in self._WORKSPACE_PERSONA or n["label"] in self._WORKSPACE_UTILITY or n["label"] in self._ENGINE_SYSTEM:
                    continue  # Used via engine syscall or persona system prompt
                issues.append(CapIssue(type=self.code, label=n["label"]))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        """Heavy penalty for high unused ratio."""
        total = ctx.by_type.get("skill", 0)
        if total == 0:
            return 0
        ratio = len(issues) / total
        if ratio > 0.5:
            return 20
        elif ratio > 0.3:
            return 10
        elif ratio > 0.1:
            return 5
        return 0


class OrphanAgentCheck(CapRule):
    code = "orphan_agents"
    issue_key = "orphan_agents"
    description = "Orphan agents (0 out-degree)"

    # Persona agents are selected directly by users/routing, not via skill/workflow binding
    _WORKSPACE_PERSONA = {
        "test-engineer", "debugger", "documentation-writer",
        "meta_agent", "performance-analyzer", "planning_agent",
        "secure-reviewer", "materials_chat",
    }

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        for nid, n in ctx.nodes.items():
            if n["type"] in ("agent", "workspace_agent") and ctx.out_degree.get(nid, 0) == 0:
                if n["label"] in self._WORKSPACE_PERSONA:
                    continue  # Persona agent — selected directly, not via binding
                issues.append(CapIssue(type=self.code, label=n["label"]))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        total = ctx.by_type.get("agent", 0)
        if total == 0:
            return 0
        ratio = len(issues) / total
        if ratio > 0.5:
            return 15
        elif ratio > 0.2:
            return 8
        elif ratio > 0:
            return 3
        return 0


class UnresolvedRefCheck(CapRule):
    code = "unresolved_refs"
    issue_key = "unresolved_refs"
    description = "Unresolved agent→skill references"

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        for e in ctx.edges:
            if e.get("relation") == "requires" and e["to"] not in ctx.nodes:
                from_node = ctx.nodes.get(e["from"], {})
                issues.append(CapIssue(
                    type=self.code,
                    label=e["from"],
                    detail=e["to"],
                    extra={"agent": e["from"], "target": e["to"],
                           "target_type": from_node.get("type", "unknown")},
                ))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        return min(len(issues) * 2, 20)


class EntryPointDupCheck(CapRule):
    code = "entry_point_duplicates"
    issue_key = "entry_point_duplicates"
    description = "Duplicate entry points (same capability, multiple routes)"

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        for nid, n in ctx.nodes.items():
            if n.get("type") == "entry_point" and n.get("has_duplicate"):
                issues.append(CapIssue(
                    type=self.code,
                    label=n["label"],
                    extra={
                        "capability": n["label"],
                        "files": n.get("files", []),
                        "detail": n.get("_issue_detail", ""),
                    },
                ))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        return min(len(issues) * 3, 15)


class TopHubsCheck(CapRule):
    code = "top_hubs"
    issue_key = None  # Not an issue — informative metric
    description = "Top nodes by degree"

    def check(self, ctx: CapContext) -> List[CapIssue]:
        return []  # Informational only, not issues

    def bonus(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        if not ctx.nodes:
            return 0
        avg_degree = (2 * len(ctx.edges)) / len(ctx.nodes)
        if avg_degree >= 2.0:
            return 5
        elif avg_degree >= 1.0:
            return 2
        return 0


class NestedAssetCheck(CapRule):
    """Detect assets installed at nested paths (broken zip import artifact)."""
    code = "nested_assets"
    issue_key = "nested_assets"
    description = "Assets installed at nested paths (broken zip import)"

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        for nid, n in ctx.nodes.items():
            if n.get("nested") and n.get("nesting_depth", 0) > 1:
                issues.append(CapIssue(
                    type=self.code,
                    label=n["label"],
                    detail=f"depth={n.get('nesting_depth')} — should be flat under root",
                    extra={"node_id": nid, "type": n["type"], "path": n.get("path", "")},
                ))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        return min(len(issues) * 10, 30)


class HandlerMissingCheck(CapRule):
    """Detect skills where execution_type=handler but handler.py doesn't exist."""
    code = "handler_missing"
    issue_key = "handler_missing"
    description = "handler.py missing for handler-type skills"

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        for nid, n in ctx.nodes.items():
            if n.get("type") not in ("skill", "workspace_skill"):
                continue
            exec_type = n.get("execution_type", "")
            has_handler = n.get("has_handler", False)
            if exec_type == "handler" and not has_handler:
                issues.append(CapIssue(
                    type=self.code,
                    label=n["label"],
                    detail=f"execution_type=handler but handler.py not found at {n.get('path', '')}",
                    extra={"node_id": nid, "path": n.get("path", "")},
                ))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        return min(len(issues) * 8, 20)


class SkillToolBindingCheck(CapRule):
    """Detect skills with tools references that don't match registered tools."""
    code = "skill_tool_gaps"
    issue_key = "skill_tool_gaps"
    description = "Skill→tool references where tool doesn't exist"

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        # Collect all tool node IDs
        tool_ids = {nid for nid, n in ctx.nodes.items() if n.get("type") in ("tool", "syscall")}
        for e in ctx.edges:
            if e.get("relation") == "requires" and e["from"].startswith(("skill:", "workspace_skill:")):
                target = e["to"]
                # tool:* references need to match registered tools
                if target.startswith("tool:") and target not in tool_ids:
                    issues.append(CapIssue(
                        type=self.code,
                        label=e["from"],
                        detail=target,
                        extra={"skill": e["from"], "missing_tool": target},
                    ))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        return min(len(issues) * 3, 15)


class SyscallCoverageCheck(CapRule):
    """Detect very low syscall usage coverage (indicates extraction gap)."""
    code = "syscall_coverage"
    issue_key = None  # informational
    description = "Syscall usage extraction coverage"

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        skill_count = ctx.by_type.get("skill", 0)
        if skill_count == 0:
            return issues
        uses_edges = sum(1 for e in ctx.edges if e.get("relation") == "uses")
        if uses_edges == 0 and skill_count > 10:
            issues.append(CapIssue(
                type=self.code,
                label="syscall_extraction",
                detail=f"0 uses edges for {skill_count} skills — extraction may be failing",
            ))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        return min(len(issues) * 2, 5)


class RuntimeEvalCheck(CapRule):
    """Check if agents have runtime evaluation data."""

    code = "runtime_eval"
    issue_key = "runtime_eval"
    description = "Agent has no runtime evaluation data"

    _EVAL_DIR = str(Path(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))) / "eval_results")

    def __init__(self):
        super().__init__()
        Path(self._EVAL_DIR).mkdir(parents=True, exist_ok=True)

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        for nid, n in ctx.nodes.items():
            if n.get("type") not in ("agent", "workspace_agent"):
                continue
            agent_id = n["label"]
            result_files = list(Path(self._EVAL_DIR).glob(f"{agent_id}_*.json"))
            if not result_files:
                issues.append(CapIssue(
                    type=self.code,
                    label=agent_id,
                    detail="No runtime evaluation data",
                ))
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        total = ctx.by_type.get("agent", 0) + ctx.by_type.get("workspace_agent", 0)
        if total == 0:
            return 0
        ratio = len(issues) / total
        if ratio > 0.9:
            return 5
        elif ratio > 0.5:
            return 2
        return 0


class CodeHygieneCheck(CapRule):
    """Check if agent AGENT.md references code-hygiene skill (Karpathy principles).
    
    Tests for either:
    1. 'code-hygiene' in required_skills → explicitly adopted
    2. Keywords in SOP body → implicitly applied
    """

    code = "code_hygiene"
    issue_key = "code_hygiene"
    description = "Agent not using code-hygiene principles (Karpathy 4 rules)"

    _HYGIENE_KW = re.compile(
        r"think before cod|simplicity first|surgical|goal.driven|验收标准|目标驱动|code.hygiene",
        re.IGNORECASE
    )

    def check(self, ctx: CapContext) -> List[CapIssue]:
        issues = []
        for nid, n in ctx.nodes.items():
            if n.get("type") not in ("agent", "workspace_agent"):
                continue
            ag_path = n.get("path", "")
            if not ag_path:
                continue
            md_file = Path(ag_path) / "AGENT.md"
            if not md_file.exists():
                continue
            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
                if self._HYGIENE_KW.search(text):
                    continue  # Already has hygiene principles
                issues.append(CapIssue(
                    type=self.code,
                    label=n["label"],
                    detail="missing code-hygiene principles (add 'code-hygiene' to required_skills)",
                ))
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return issues

    def penalty(self, ctx: CapContext, issues: List[CapIssue]) -> float:
        total = ctx.by_type.get("agent", 0) + ctx.by_type.get("workspace_agent", 0)
        if total == 0:
            return 0
        ratio = len(issues) / total
        if ratio > 0.8:
            return 5
        elif ratio > 0.4:
            return 2
        return 0


# ============================================================
# Registry
# ============================================================

class CapHealthRegistry:
    """Runs all capability health rules against a graph and computes score."""

    def __init__(self):
        self._rules: List[CapRule] = [cls() for cls in _all_rules()]

    def register(self, rule: CapRule) -> None:
        self._rules.append(rule)

    def run(self, graph_result) -> CapHealthReport:
        """Produce a health report from a CapabilityGraphResult."""
        nodes = graph_result.nodes
        edges = graph_result.edges

        # Build shared context (once)
        out_degree: Dict[str, int] = defaultdict(int)
        in_degree: Dict[str, int] = defaultdict(int)
        neighbors: Dict[str, List[str]] = defaultdict(list)

        for e in edges:
            src, dst = e["from"], e["to"]
            out_degree[src] += 1
            in_degree[dst] += 1
            neighbors[src].append(dst)
            neighbors[dst].append(src)

        total_degree = {nid: out_degree.get(nid, 0) + in_degree.get(nid, 0) for nid in nodes}

        by_type: Dict[str, int] = defaultdict(int)
        for n in nodes.values():
            t = n["type"]
            # Aggregate engine + workspace scopes for backward-compatible checks
            by_type[t] += 1
            # Also add merged counts for rules that check "skill" / "agent" generically
            if t in ("workspace_agent",):
                by_type["agent"] += 1
            elif t in ("workspace_skill",):
                by_type["skill"] += 1

        ctx = CapContext(
            nodes=nodes, edges=edges,
            in_degree=dict(in_degree), out_degree=dict(out_degree),
            neighbors=dict(neighbors), total_degree=total_degree,
            by_type=dict(by_type),
        )

        # Run all rules
        all_issues: Dict[str, List] = {}
        top_hubs: List[Dict[str, Any]] = []
        score = 100.0

        for rule in self._rules:
            try:
                issues = rule.check(ctx)
                if rule.issue_key:
                    # Format issues according to expected consumer format
                    if rule.issue_key == "unused_skills":
                        all_issues[rule.issue_key] = [i.label for i in issues]
                    elif rule.issue_key == "orphan_agents":
                        all_issues[rule.issue_key] = [i.label for i in issues]
                    elif rule.issue_key == "unresolved_refs":
                        all_issues[rule.issue_key] = [
                            {"agent": i.extra["agent"], "target": i.extra["target"],
                             "target_type": i.extra["target_type"]}
                            for i in issues
                        ]
                    elif rule.issue_key == "code_hygiene":
                        all_issues[rule.issue_key] = [
                            {"agent": i.label, "missing": i.detail}
                            for i in issues
                        ]
                    elif rule.issue_key == "entry_point_duplicates":
                        all_issues[rule.issue_key] = [
                            {"capability": i.extra["capability"],
                             "files": i.extra["files"],
                             "detail": i.extra["detail"]}
                            for i in issues
                        ]
                    else:
                        # Generic flattening for any new issue types
                        all_issues[rule.issue_key] = [i.extra for i in issues]

                if rule.code == "top_hubs":
                    top_hubs = sorted(
                        [{"id": nid, "label": nodes[nid]["label"],
                          "type": nodes[nid]["type"], "degree": total_degree[nid]}
                         for nid in nodes],
                        key=lambda x: x["degree"], reverse=True,
                    )[:15]

                score -= rule.penalty(ctx, issues)
                score += rule.bonus(ctx, issues)
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        # Structural penalties (not per-rule)
        total_tools = by_type.get("tool", 0)
        total_mcp = by_type.get("mcp_server", 0)
        if total_tools == 0:
            score -= 5
        if total_mcp == 0 and len(nodes) > 0:
            score -= 2

        score = max(0, min(100, score))

        # Grade
        if score >= 90:
            grade = "A"
        elif score >= 75:
            grade = "B"
        elif score >= 60:
            grade = "C"
        elif score >= 40:
            grade = "D"
        else:
            grade = "F"

        # Blast radius
        top_blast = _compute_blast(nodes, out_degree, neighbors, top_n=10)

        total_agents = by_type.get("agent", 0)
        total_skills = by_type.get("skill", 0)
        used_skills = total_skills - len(all_issues.get("unused_skills", []))

        return CapHealthReport(
            score=round(score, 1),
            grade=grade,
            signals={
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "agents": total_agents,
                "skills": total_skills,
                "used_skills": used_skills,
                "tools": total_tools,
                "mcp_servers": total_mcp,
                "avg_degree": round((2 * len(edges)) / len(nodes), 2) if nodes else 0,
            },
            issues=all_issues,
            top_hubs=top_hubs,
            top_blast=top_blast,
            by_type=dict(by_type),
        )


def _compute_blast(
    nodes: Dict[str, Dict[str, Any]],
    out_degree: Dict[str, int],
    neighbors: Dict[str, List[str]],
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """BFS blast radius: how many nodes are reachable from each node (forward only)."""
    results: List[Dict[str, Any]] = []
    for nid in nodes:
        visited: Set[str] = set()
        queue = [nid]
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            for nb in neighbors.get(cur, []):
                if nb not in visited:
                    queue.append(nb)
        blast = len(visited) - 1
        if blast > 0:
            results.append({"id": nid, "label": nodes[nid]["label"],
                           "type": nodes[nid]["type"], "blast": blast})
    results.sort(key=lambda x: x["blast"], reverse=True)
    return results[:top_n]


def _all_rules() -> List[type]:
    """Collect all CapRule subclasses defined above."""
    import sys
    rules = []
    current_module = sys.modules[__name__]
    for name in dir(current_module):
        obj = getattr(current_module, name)
        if (isinstance(obj, type)
                and issubclass(obj, CapRule)
                and obj is not CapRule
                and not name.startswith("_")):
            rules.append(obj)
    return rules


# ============================================================
# Singleton
# ============================================================

_registry: Optional[CapHealthRegistry] = None


def get_cap_registry() -> CapHealthRegistry:
    global _registry
    if _registry is None:
        _registry = CapHealthRegistry()
    return _registry
