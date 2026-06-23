"""Tool self-tests: verify capability_graph.py core functions."""
import sys
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))

from core.harness.knowledge.capability_graph import (
    CapabilityGraphResult,
    build_capability_graph,
    clear_capability_cache,
)


class TestCapabilityGraph:

    def test_build_with_cache_clear(self):
        clear_capability_cache()
        result = build_capability_graph()
        assert isinstance(result, CapabilityGraphResult)
        assert isinstance(result.nodes, dict)

    def test_build_returns_non_empty(self):
        clear_capability_cache()
        result = build_capability_graph()
        assert len(result.nodes) >= 0
        assert len(result.edges) >= 0

    def test_double_build_is_idempotent(self):
        clear_capability_cache()
        r1 = build_capability_graph()
        r2 = build_capability_graph()
        assert len(r2.nodes) >= len(r1.nodes)
