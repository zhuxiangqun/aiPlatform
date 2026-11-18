"""N09 K23 — diagnostician / convergence / case_learning / recon GraphIndex tenant."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



def _assert_no_bare_loads(rel: str) -> None:
    text = (_repo_root() / rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_system_diagnostician_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/system_diagnostician.py").read_text(encoding="utf-8")
    assert "tenant_id: str = \"\"" in text
    assert "_resolve_graph_tenant" in text
    assert 'GraphIndex.load("knowledge-atom", tenant_id=self._tenant_id)' in text
    assert "GraphIndex.load(domain_id, tenant_id=self._tenant_id)" in text
    assert 'GraphIndex.load("knowledge-atom", tenant_id=_resolve_graph_tenant())' in text
    _assert_no_bare_loads(
        "aiPlat-core/core/harness/knowledge/system_diagnostician.py"
    )


def test_convergence_engine_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/convergence_engine.py").read_text(encoding="utf-8")
    assert "self._tenant_id" in text
    assert 'GraphIndex.load("knowledge-atom", tenant_id=self._tenant_id)' in text
    _assert_no_bare_loads(
        "aiPlat-core/core/harness/knowledge/convergence_engine.py"
    )


def test_ontology_case_learning_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/ontology_case_learning.py").read_text(encoding="utf-8")
    assert "tenant_id: str = \"\"" in text
    assert "GraphIndex.load(self.domain_id, tenant_id=self._tenant_id)" in text
    _assert_no_bare_loads(
        "aiPlat-core/core/harness/knowledge/ontology_case_learning.py"
    )


def test_recon_subgraph_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/recon_subgraph.py").read_text(encoding="utf-8")
    assert "tenant_id: str = \"\"" in text
    assert "GraphIndex.load(target_domain, tenant_id=tid)" in text
    _assert_no_bare_loads(
        "aiPlat-core/core/harness/knowledge/recon_subgraph.py"
    )


def test_diagnostician_init_resolves_tenant(monkeypatch):
    from core.harness.knowledge import system_diagnostician as sd

    seen = {}

    class _G:
        pass

    def _fake_load(domain_id, tenant_id="default"):
        seen.setdefault("loads", []).append((domain_id, tenant_id))
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t23",
    )
    eng = sd.SystemDiagnostician()
    assert eng._tenant_id == "n09-t23"
    eng._ensure_loaded()
    assert ("knowledge-atom", "n09-t23") in seen.get("loads", [])


def test_convergence_init_resolves_tenant(monkeypatch):
    from core.harness.knowledge import convergence_engine as ce

    seen = {}

    class _G:
        pass

    def _fake_load(domain_id, tenant_id="default"):
        seen.setdefault("loads", []).append((domain_id, tenant_id))
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t23",
    )
    monkeypatch.setattr(
        ce.ConvergenceEngine,
        "_load_config",
        lambda self: {},
    )
    eng = ce.ConvergenceEngine()
    assert eng._tenant_id == "n09-t23"
    eng._ensure_loaded()
    assert ("knowledge-atom", "n09-t23") in seen.get("loads", [])


def test_recon_merge_to_loads_tenant(monkeypatch):
    from core.harness.knowledge import recon_subgraph as rs

    seen = {}

    class _Node:
        entity_id = "e1"
        entity_name = "E1"
        class_name = "Thing"
        source_doc_id = ""
        out_edges = []

    class _Src:
        def __init__(self):
            self._nodes = {"e1": _Node()}

        def get_node(self, _nid):
            return None

        def add_entity(self, *a, **k):
            return None

        def add_relation(self, *a, **k):
            return None

        def save(self):
            return None

    class _Target(_Src):
        pass

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _Target()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.__init__",
        lambda self, domain_id, **kw: None,
    )

    recon = rs.ReconSubgraph("run-k23", data_dir="/tmp/recon-k23-test")
    recon.graph = _Src()
    recon.merge_to("demo-domain", tenant_id="n09-t23")
    assert seen.get("tenant_id") == "n09-t23"
    assert seen.get("domain_id") == "demo-domain"
