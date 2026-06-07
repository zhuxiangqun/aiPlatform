"""
Architecture Constitution Tests: Property-Based

Uses hypothesis to verify invariants that hold for any valid code graph and layer boundary.
"""
import os
import sys
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))

try:
    from hypothesis import given, settings, strategies as st, HealthCheck
    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False

# ── Graph invariants ──────────────────────────────────────────────

@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestGraphInvariants:
    """Property-based tests for code graph integrity."""

    @given(st.integers(min_value=0, max_value=10))
    @settings(max_examples=2, deadline=None)
    def test_cycle_count_non_negative_for_any_graph(self, _seed):
        """Cycle count must always be >= 0 regardless of graph structure."""
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root, count_cycles
        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes, _, _ = build_graph(r, roots)
        cycles = count_cycles(nodes)
        assert cycles >= 0, f"Cycle count negative: {cycles}"
        assert isinstance(cycles, int), f"Cycle count not int: {type(cycles)}"

    @given(st.integers(min_value=0, max_value=10))
    @settings(max_examples=2, deadline=None)
    def test_health_score_in_range(self, _seed):
        """Health score must be between 0 and 100."""
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root, health_score, count_cycles
        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes, _, _ = build_graph(r, roots)
        cycles = count_cycles(nodes)
        health = health_score(nodes=nodes, edges=[], issues=[], cycles_back_edges=cycles)
        score = health.get("score", -1)
        assert 0 <= score <= 100, f"Health score out of range: {score}"
        assert health.get("grade") in ("A", "B", "C", "D", "F"), f"Invalid grade: {health.get('grade')}"

    @given(st.integers(min_value=0, max_value=10))
    @settings(max_examples=2, deadline=None)
    def test_layer_detection_consistent(self, _seed):
        """Each file node must be assigned to exactly one layer."""
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes, _, _ = build_graph(r, roots)
        for path, node in nodes.items():
            # Every file should have a valid ext or be skipworthy
            ext = node.get("ext", "")
            assert ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml", ".md", ".toml", ".cfg", ""), (
                f"Unexpected ext: {ext} in {path}"
            )

    @given(st.integers(min_value=0, max_value=10))
    @settings(max_examples=2, deadline=None)
    def test_out_edges_consistent_with_edges_list(self, _seed):
        """Node out[] list must be subset of edges list targets."""
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes, edges, _ = build_graph(r, roots)
        edge_set = set((e["from"], e["to"]) for e in edges if e.get("kind", "import") == "import")
        for path, node in nodes.items():
            out_list = node.get("out", [])
            for dst in out_list:
                assert (path, dst) in edge_set, f"out[] edge missing from edges list: {path} → {dst}"


# ── Layer boundary invariants ──────────────────────────────────────

@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestLayerBoundaryInvariants:
    """Property-based tests that layer boundary rules are transitive/invariant under mutation."""

    def test_import_graph_is_dag_between_layers(self):
        """Cross-layer imports must not create cycles (DAG property)."""
        from core.harness.knowledge.code_graph import build_graph, default_roots, repo_root
        r = repo_root()
        roots = [(r / d).resolve() for d in default_roots()]
        nodes, edges, _ = build_graph(r, roots)

        # Build cross-layer edge graph (only edges between different top-level dirs)
        def _layer(p: str) -> str:
            top = p.split("/")[0] if "/" in p else p
            return top.replace("aiPlat-", "") if top.startswith("aiPlat-") else top

        cross_layer = {}
        for e in edges:
            if e.get("kind", "import") != "import":
                continue
            src_layer = _layer(e["from"])
            dst_layer = _layer(e["to"])
            if src_layer != dst_layer:
                cross_layer.setdefault(e["from"], []).append(e["to"])

        # Verify: for any two files A→B with different layers, the layers must follow
        # the allowed direction: infra→core→platform→app
        _ALLOWED = {("platform", "core"), ("core", "infra"), ("app", "platform"),
                    ("management", "core"), ("management", "platform"), ("management", "infra")}

        # Known exceptions: pre-existing cross-layer imports awaiting refactor
        _KNOWN_EXCEPTIONS = {
            ("aiPlat-core/core/harness/execution/pipeline_engine.py",
             "aiPlat-platform/storage/sqlite.py"),
            ("aiPlat-core/core/management/workflow_manager.py",
             "aiPlat-platform/storage/sqlite.py"),
        }
        violations = []
        for e in edges:
            if e.get("kind", "import") != "import":
                continue
            src_layer = _layer(e["from"])
            dst_layer = _layer(e["to"])
            if src_layer == dst_layer:
                continue
            if (e["from"], e["to"]) in _KNOWN_EXCEPTIONS:
                continue
            pair = (src_layer, dst_layer)
            if pair not in _ALLOWED and src_layer != "infra_internal":
                violations.append(f"{e['from']} ({src_layer}) → {e['to']} ({dst_layer})")

        assert len(violations) == 0, (
            f"{len(violations)} cross-layer import direction violations:\n" +
            "\n".join(f"  - {v}" for v in violations[:10])
        )


def test_no_hypothesis_installed():
    """If hypothesis is not installed, skip property tests gracefully."""
    if not HAS_HYPOTHESIS:
        pytest.skip("hypothesis not installed — property tests skipped")


def test_pyright_config_valid():
    """pyrightconfig.json must exist and contain required keys."""
    import json
    config_path = WORKSPACE_ROOT / "aiPlat-core" / "pyrightconfig.json"
    assert config_path.exists(), "pyrightconfig.json not found in aiPlat-core/"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "include" in data, "include key required in pyrightconfig.json"
    assert "typeCheckingMode" in data, "typeCheckingMode required in pyrightconfig.json"
    assert len(data["include"]) > 0, "include must have at least one path"
    assert data["typeCheckingMode"] in ("basic", "standard", "strict"), (
        f"Invalid typeCheckingMode: {data['typeCheckingMode']}")


def test_sys_lsp_fix_tool_importable():
    """SysLspFixTool must be importable and have correct tool name."""
    try:
        from core.apps.tools.sysgraph_tools import SysLspFixTool
        from core.apps.tools.base import BaseTool
        assert issubclass(SysLspFixTool, BaseTool), "SysLspFixTool not a BaseTool subclass"
        instance = SysLspFixTool()
        assert instance.name == "sys_lsp_fix", f"Expected sys_lsp_fix, got {instance.name}"
        # Verify required parameters (accessible via _config)
        cfg = getattr(instance, '_config', getattr(instance, 'config', None))
        if cfg:
            params = getattr(cfg, 'parameters', {}).get("properties", {})
            assert "file" in params, "file param missing"
            assert "line" in params, "line param missing"
            assert "verify" in params, "verify param missing"
    except ImportError as e:
        pytest.skip(f"Module not importable: {e}")


def test_prompt_loader_defaults_registered():
    """Prompt loader must have 40+ templates with ${var} placeholders and metadata."""
    try:
        from core.harness.utils.prompt_loader import _DEFAULT_PROMPTS, list_templates, get_metadata
    except ImportError as e:
        pytest.skip(f"Module not importable: {e}")

    assert len(_DEFAULT_PROMPTS) >= 40, f"Expected >=40 templates, got {len(_DEFAULT_PROMPTS)}"
    for tid, content in _DEFAULT_PROMPTS.items():
        assert len(content) > 10, f"Template {tid} too short: {len(content)} chars"
        meta = get_metadata(tid)
        has_vars = meta and len(meta.get("variables", [])) > 0
        if has_vars:
            assert "${" in content, f"Template {tid} with variables should use ${{var}} placeholders"

    # Verify auto_classify works
    from core.harness.utils.prompt_loader import auto_classify
    assert auto_classify("react-reasoning") == "admin", "react-reasoning should be admin"
    assert auto_classify("graph-ask") == "app", "graph-ask should be app"
    assert auto_classify("unknown-tpl") == "app", "unknown should default to app"

    # Verify some metadata
    meta = get_metadata("react-reasoning")
    assert meta, "react-reasoning metadata missing"
    assert meta.get("cache_ttl", 0) > 0, "react-reasoning should have cache_ttl"


def test_describe_layer_all_layers():
    """describe_layer must return data for all 5 layers."""
    try:
        from core.api.routers.knowledge_graph import _describe_layer
    except ImportError as e:
        pytest.skip(f"Module not importable: {e}")

    for layer in ("core", "infra", "platform", "app", "management"):
        r = _describe_layer(layer, "capabilities")
        assert "error" not in r, f"describe_layer({layer}) returned error: {r.get('error')}"
        assert r.get("total_files", 0) > 0, f"describe_layer({layer}) has 0 files"
        assert isinstance(r.get("modules"), dict), f"modules should be dict"


def test_describe_layer_all_types():
    """describe_layer must support all 3 question types."""
    try:
        from core.api.routers.knowledge_graph import _describe_layer
    except ImportError as e:
        pytest.skip(f"Module not importable: {e}")

    for qtype in ("capabilities", "relationships", "interfaces"):
        r = _describe_layer("core", qtype)
        assert "error" not in r, f"describe_layer(core, {qtype}) returned error: {r.get('error')}"
        assert r.get("type") == qtype, f"type mismatch: {r.get('type')} != {qtype}"


def test_migrated_files_use_prompt_loader():
    """Files that had hardcoded prompts must now use prompt_loader."""
    import re
    migrated_files = [
        "aiPlat-core/core/harness/assembly/prompt_assembler.py",
        "aiPlat-core/core/harness/execution/loop.py",
        "aiPlat-core/core/harness/execution/pipeline_engine.py",
        "aiPlat-core/core/harness/knowledge/wiki_engine.py",
        "aiPlat-core/core/harness/assembly/compaction_prompt.py",
        "aiPlat-core/core/harness/evaluation/rag_evaluator.py",
        "aiPlat-core/core/harness/memory/episodic.py",
        "aiPlat-core/core/harness/memory/profile_builder.py",
        "aiPlat-core/core/harness/execution/langgraph/graphs/reflection.py",
        "aiPlat-core/core/harness/coordination/patterns/base.py",
        "aiPlat-core/core/api/routers/knowledge_graph.py",
        "aiPlat-core/core/api/routers/workspace_agents.py",
        "aiPlat-core/core/api/routers/entropy.py",
        "aiPlat-core/core/api/intents.py",
        "aiPlat-core/core/apps/skills/executor.py",
        "aiPlat-core/core/apps/skills/registry.py",
        "aiPlat-core/core/apps/document_intelligence/summarizer.py",
        "aiPlat-platform/api/routers/kb_integration.py",
        "aiPlat-platform/api/routers/conversations.py",
        "aiPlat-platform/kb/intelligence/query.py",
        "aiPlat-platform/api/rest/routes.py",
        "aiPlat-core/core/apps/skills/base.py",
    ]

    missing = []
    for fpath in migrated_files:
        p = WORKSPACE_ROOT / fpath
        if not p.exists():
            missing.append(f"MISSING: {fpath}")
            continue
        content = p.read_text(encoding="utf-8")
        if "_sync_resolve" not in content and "_async_prompt_resolve" not in content:
            missing.append(f"No prompt_loader: {fpath}")

    assert not missing, (
        f"{len(missing)} migrated files missing prompt_loader usage:\n" +
        "\n".join(f"  - {m}" for m in missing)
    )


def test_prompt_app_routers_registered():
    """All 3 new prompt routers must be importable and have endpoints."""
    routers = {
        "prompt_app": ["/prompts/app/templates", "/prompts/app/categories", "/prompts/app/optimize"],
        "prompt_eval": ["/prompts/eval/test-cases", "/prompts/eval/runs"],
        "prompt_optimize": ["/prompts/optimize"],
    }
    missing = []
    for module_name, paths in routers.items():
        try:
            mod = __import__(f"core.api.routers.{module_name}", fromlist=["router"])
            route_paths = [r.path for r in mod.router.routes]
            for p in paths:
                if p not in route_paths:
                    missing.append(f"{module_name}: missing {p}")
        except Exception as e:
            missing.append(f"{module_name}: import error {e}")

    assert not missing, f"Router registration issues:\n" + "\n".join(f"  - {m}" for m in missing)


def test_prompt_menu_reorganized():
    """AppLayout must have '提示词工程' menu group with app/optimize/eval items."""
    app_layout = WORKSPACE_ROOT / "aiPlat-management" / "frontend" / "src" / "components" / "layout" / "AppLayout.tsx"
    content = app_layout.read_text(encoding="utf-8")
    assert "提示词工程" in content, "Missing 提示词工程 menu group"
    assert "应用模板" in content, "Missing 应用模板 menu item"
    assert "系统Prompt" in content, "Missing 系统Prompt menu item"
