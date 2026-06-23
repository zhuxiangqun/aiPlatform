"""Tool self-tests: verify graph_index.py and graph_traversal.py."""
import sys
from pathlib import Path
import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "aiPlat-core"))


class TestGraphImports:

    def test_graph_index_imports(self):
        from core.harness.ontology_engine.graph_index import (
            GraphNode,
            GraphEdge,
            GraphIndex,
        )
        assert GraphNode is not None
        assert GraphEdge is not None
        assert GraphIndex is not None

    def test_graph_index_init(self):
        from core.harness.ontology_engine.graph_index import GraphIndex
        g = GraphIndex(domain_id="test-domain")
        assert g is not None

    def test_graph_index_basic_crud(self):
        from core.harness.ontology_engine.graph_index import GraphIndex
        g = GraphIndex(domain_id="test-domain")
        g.add_entity("e1", "Test", "C")
        node = g.find_by_name("Test")
        assert node is not None

    def test_graph_traversal_imports(self):
        from core.harness.ontology_engine.graph_traversal import (
            traverse,
            traverse_multi,
        )
        assert callable(traverse)
        assert callable(traverse_multi)
