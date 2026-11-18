"""N09 K26 — ontology_engine GraphIndex tenant (engine/shard/cleanup/…)."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



def _assert_no_bare_loads(rel: str) -> None:
    text = Path(rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_engine_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/ontology_engine/engine.py").read_text(
        encoding="utf-8"
    )
    assert "GraphIndex.load(self._domain.id, tenant_id=self._tenant_id)" in text
    assert 'cache_key = f"{tid}::{domain_id}"' in text
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in text
    _assert_no_bare_loads("aiPlat-core/core/harness/ontology_engine/engine.py")


def test_supporting_modules_source_wires_tenant():
    for rel in (
        "aiPlat-core/core/harness/ontology_engine/sharded_graph.py",
        "aiPlat-core/core/harness/ontology_engine/run_context_builder.py",
        "aiPlat-core/core/harness/ontology_engine/action_registry.py",
        "aiPlat-core/core/harness/ontology_engine/knowledge_gap_detector.py",
        "aiPlat-core/core/harness/ontology_engine/cleanup.py",
        "aiPlat-core/core/harness/ontology_engine/business_event_bridge.py",
    ):
        text = Path(rel).read_text(encoding="utf-8")
        assert "tenant_id" in text and (
            "_resolve_graph_tenant" in text or "self._tenant_id" in text
        ), rel
        _assert_no_bare_loads(rel)


def test_get_graph_caches_per_tenant(monkeypatch):
    from core.harness.ontology_engine import engine as eng

    eng._graph_cache.clear()
    eng._graph_cache_order.clear()
    seen = []

    class _G:
        pass

    def _fake_load(domain_id, tenant_id="default"):
        seen.append((domain_id, tenant_id))
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    g1 = eng.get_graph("demo", tenant_id="n09-t26a")
    g2 = eng.get_graph("demo", tenant_id="n09-t26b")
    g1b = eng.get_graph("demo", tenant_id="n09-t26a")
    assert ("demo", "n09-t26a") in seen
    assert ("demo", "n09-t26b") in seen
    assert seen.count(("demo", "n09-t26a")) == 1  # cache hit
    assert g1 is g1b
    assert g1 is not g2


def test_cleanup_loads_tenant(monkeypatch):
    from core.harness.ontology_engine import cleanup as cu

    seen = {}

    class _G:
        def __len__(self):
            return 0

        _nodes = {}

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    cu.get_entity_trace(doc_id="d1", domain_id="demo", tenant_id="n09-t26")
    assert seen.get("tenant_id") == "n09-t26"
    assert seen.get("domain_id") == "demo"
