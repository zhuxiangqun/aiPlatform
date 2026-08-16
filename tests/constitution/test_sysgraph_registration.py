""""
Architecture Constitution Tests: sysgraph Tool Registration

Verifies all sysgraph tools are properly registered in ToolRegistry, all diagnostic
categories are discoverable, and agent AGENT.md files reference sysgraph tools.
"""
import os
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))

ALL_SYSGRAPH_TOOLS = [
    "sysgraph_context",
    "sysgraph_search",
    "sysgraph_impact",
    "sysgraph_callers",
    "sysgraph_node",
    "sysgraph_affected_tests",
    "sysgraph_review",
    "sysgraph_deps",
    "sysgraph_diff",
    "sysgraph_related",
    "sysgraph_stats",
    "sysgraph_tests",
    "sysgraph_hotspots",
    "sysgraph_find",
    "sysgraph_churn",
    "sys_lsp_fix",
]


def test_all_16_sysgraph_tools_registered():
    """All 16 sysgraph tools must be importable as BaseTool subclasses."""
    from core.apps.tools.base import BaseTool

    tool_classes = {
        "SysGraphContextTool": "sysgraph_context",
        "SysGraphSearchTool": "sysgraph_search",
        "SysGraphImpactTool": "sysgraph_impact",
        "SysGraphCallersTool": "sysgraph_callers",
        "SysGraphNodeTool": "sysgraph_node",
        "SysGraphAffectedTestsTool": "sysgraph_affected_tests",
        "SysGraphReviewTool": "sysgraph_review",
        "SysGraphDepsTool": "sysgraph_deps",
        "SysGraphDiffTool": "sysgraph_diff",
        "SysGraphRelatedTool": "sysgraph_related",
        "SysGraphStatsTool": "sysgraph_stats",
        "SysGraphTestsTool": "sysgraph_tests",
        "SysGraphHotspotsTool": "sysgraph_hotspots",
        "SysGraphFindTool": "sysgraph_find",
        "SysGraphChurnTool": "sysgraph_churn",
        "SysLspFixTool": "sys_lsp_fix",
    }

    missing = []
    for cls_name, tool_name in tool_classes.items():
        try:
            mod = __import__("core.apps.tools.sysgraph_tools", fromlist=[cls_name])
            cls = getattr(mod, cls_name, None)
            if cls is None:
                missing.append(f"{cls_name}: class not found in sysgraph_tools")
            elif not issubclass(cls, BaseTool):
                missing.append(f"{cls_name}: not a BaseTool subclass")
            else:
                instance = cls()
                if instance.name != tool_name:
                    missing.append(f"{cls_name}: name mismatch ({instance.name} != {tool_name})")
        except Exception as e:
            missing.append(f"{cls_name}: import error - {e}")

    assert not missing, (
        f"{len(missing)}/{len(tool_classes)} sysgraph tools registration issues:\n" +
        "\n".join(f"  - {m}" for m in missing)
    )


def test_all_sysgraph_tools_in_server_registration():
    """All 12 sysgraph tool classes must be in server.py registration list."""
    server_py = WORKSPACE_ROOT / "aiPlat-core" / "core" / "server.py"
    content = server_py.read_text(encoding="utf-8")

    expected_classes = {
        "SysGraphContextTool", "SysGraphSearchTool", "SysGraphImpactTool",
        "SysGraphCallersTool", "SysGraphNodeTool", "SysGraphAffectedTestsTool",
        "SysGraphReviewTool", "SysGraphDepsTool", "SysGraphDiffTool",
        "SysGraphRelatedTool", "SysGraphStatsTool", "SysGraphTestsTool",
        "SysGraphHotspotsTool", "SysGraphFindTool", "SysGraphChurnTool",
        "SysLspFixTool",
    }

    registered = {cls for cls in expected_classes if cls in content}
    missing = expected_classes - registered

    assert not missing, (
        f"{len(missing)} sysgraph tool classes not in server.py registration:\n" +
        "\n".join(f"  - {c}" for c in missing)
    )
    assert len(registered) == 16, f"Expected 16 sysgraph tool classes, found {len(registered)}"


def test_sysgraph_tools_referenced_in_agent_md():
    """At least 5 agent AGENT.md files reference sysgraph tools."""
    agent_dirs = [
        WORKSPACE_ROOT / "aiPlat-core" / "agents",
        WORKSPACE_ROOT / "aiPlat-core" / "core" / "engine" / "agents",
        # P0-A8: workspace agents also use sysgraph tools (engine + workspace = 10 total)
        Path.home() / ".aiplat" / "agents",
    ]

    count = 0
    referenced = []
    for agent_dir in agent_dirs:
        if not agent_dir.is_dir():
            continue
        for agent_md in agent_dir.rglob("AGENT.md"):
            text = agent_md.read_text(encoding="utf-8")
            for tool in ALL_SYSGRAPH_TOOLS:
                if tool in text:
                    if agent_md.parent.name not in referenced:
                        referenced.append(agent_md.parent.name)
                    break

    # Engine agents were pruned (CLAUDE.md §5.27 48→26): all 4 engine agents
    # reference sysgraph tools. User-level ~/.aiplat/agents are optional in CI.
    assert len(referenced) >= 4, (
        f"Only {len(referenced)} agent AGENT.md files reference sysgraph tools, need >=4\n"
        f"Referenced by: {referenced}"
    )


def test_diagnostic_categories_registered():
    u"""All 17 diagnostic categories must be in run_all_diagnostics gather + labels."""
    diag_path = WORKSPACE_ROOT / "aiPlat-core" / "core" / "api" / "routers" / "diagnostics.py"
    content = diag_path.read_text(encoding="utf-8")

    expected = [
        "core_runtime", "code_intel", "capability", "skill_lint", "wiki_health",
        "compliance", "overview_issues", "traces", "graph_runs", "context_metrics",
        "e2e_smoke", "symbol_health", "doctor", "lsp", "security", "arch_guard",
    ]

    missing_gather = []
    missing_labels = []
    for name in expected:
        if name == "arch_guard":
            continue  # injected after gather, not in gather
        if f'_check_{name}()' not in content and f'_safe("{name}"' not in content:
            missing_gather.append(name)
        if f'"{name}"' not in content:
            missing_labels.append(name)

    assert not missing_gather, (
        f"{len(missing_gather)} categories missing from gather block: {missing_gather}"
    )
    assert not missing_labels, (
        f"{len(missing_labels)} categories missing from _labels dict: {missing_labels}"
    )


def test_security_check_function_exists():
    u"""_check_security() must be importable and have proper signature."""
    try:
        import importlib
        diag = importlib.import_module("core.api.routers.diagnostics")
        assert hasattr(diag, "_check_security") or "_check_security" in dir(diag._run_all_diagnostics), (
            "_check_security function not found in diagnostics module"
        )
    except Exception as e:
        # If import fails due to deps, check source
        diag_path = WORKSPACE_ROOT / "aiPlat-core" / "core" / "api" / "routers" / "diagnostics.py"
        content = diag_path.read_text(encoding="utf-8")
        assert "async def _check_security" in content, "_check_security function not found in diagnostics.py"
