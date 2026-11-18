"""N09 K22 — evolver / SECI / retrieval / path / candidate GraphIndex tenant."""
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


def test_system_evolver_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/system_evolver.py").read_text(
        encoding="utf-8"
    )
    assert "tenant_id: str = \"\"" in text
    assert "_resolve_graph_tenant" in text
    assert 'GraphIndex.load("knowledge-atom", tenant_id=self._tenant_id)' in text
    _assert_no_bare_loads("aiPlat-core/core/harness/knowledge/system_evolver.py")


def test_seci_engine_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/seci_engine.py").read_text(
        encoding="utf-8"
    )
    assert "self._tenant_id" in text
    assert 'GraphIndex.load("knowledge-atom", tenant_id=self._tenant_id)' in text
    assert "tenant_id=engine._tenant_id" in text
    _assert_no_bare_loads("aiPlat-core/core/harness/knowledge/seci_engine.py")


def test_orchestrated_retrieval_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/orchestrated_retrieval.py").read_text(encoding="utf-8")
    assert "tenant_id: str = \"\"" in text
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in text
    assert 'GraphIndex.load("ai-knowledge", tenant_id=tid)' in text
    _assert_no_bare_loads(
        "aiPlat-core/core/harness/knowledge/orchestrated_retrieval.py"
    )


def test_path_planner_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/path_planner.py").read_text(
        encoding="utf-8"
    )
    assert "tenant_id: str = \"\"" in text
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in text
    _assert_no_bare_loads("aiPlat-core/core/harness/knowledge/path_planner.py")


def test_candidate_pool_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/candidate_pool.py").read_text(
        encoding="utf-8"
    )
    assert "_resolve_graph_tenant" in text
    assert "GraphIndex.load(gap.domain_id, tenant_id=_resolve_graph_tenant())" in text
    _assert_no_bare_loads("aiPlat-core/core/harness/knowledge/candidate_pool.py")


def test_system_evolver_init_resolves_tenant(monkeypatch):
    from core.harness.knowledge import system_evolver as se

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
        lambda params=None: "n09-t22",
    )
    eng = se.SystemEvolver()
    assert eng._tenant_id == "n09-t22"
    eng._ensure_loaded()
    assert ("knowledge-atom", "n09-t22") in seen.get("loads", [])


def test_execute_path_loads_tenant(monkeypatch):
    from core.harness.knowledge import path_planner as pp

    seen = {}

    class _G:
        def get_neighbors(self, *_a, **_k):
            return []

        def get_node(self, *_a, **_k):
            return None

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    path = pp.ReasoningPath(name="demo", label="Demo", steps=[])
    pp.execute_path(path, ["e1"], "demo-domain", tenant_id="n09-t22")
    assert seen.get("tenant_id") == "n09-t22"
    assert seen.get("domain_id") == "demo-domain"
