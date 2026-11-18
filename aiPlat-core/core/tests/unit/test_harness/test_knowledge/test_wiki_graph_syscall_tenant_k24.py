"""N09 K24 — wiki routers + graph syscalls GraphIndex tenant."""
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


def test_wiki_router_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/api/routers/wiki.py").read_text(encoding="utf-8")
    assert "_resolve_graph_tenant" in text
    assert 'GraphIndex.load("ai-knowledge", tenant_id=_resolve_graph_tenant())' in text
    assert "GraphIndex.load(domain_id, tenant_id=_resolve_graph_tenant())" in text
    _assert_no_bare_loads("aiPlat-core/core/api/routers/wiki.py")


def test_sys_graph_neighbors_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/syscalls/graph.py").read_text(
        encoding="utf-8"
    )
    assert "tenant_id: str = \"\"" in text
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in text
    _assert_no_bare_loads("aiPlat-core/core/harness/syscalls/graph.py")


def test_sys_graph_validate_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/syscalls/graph_validate.py").read_text(
        encoding="utf-8"
    )
    assert "tenant_id: str = \"\"" in text
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in text
    _assert_no_bare_loads("aiPlat-core/core/harness/syscalls/graph_validate.py")


def test_sys_graph_neighbors_loads_tenant(monkeypatch):
    import asyncio
    from core.harness.syscalls import graph as gmod

    seen = {}

    class _Node:
        entity_name = "E1"
        out_edges = []
        in_edges = []

    class _G:
        def get_node(self, *_a, **_k):
            return _Node()

        def find_by_name(self, *_a, **_k):
            return _Node()

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    asyncio.get_event_loop().run_until_complete(
        gmod.sys_graph_neighbors("E1", domain_id="demo", tenant_id="n09-t24")
    )
    assert seen.get("tenant_id") == "n09-t24"
    assert seen.get("domain_id") == "demo"


def test_sys_graph_validate_loads_tenant(monkeypatch):
    import asyncio
    from core.harness.syscalls import graph_validate as gv

    seen = {}

    class _G:
        pass

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    # short-circuit after load by making subsequent ops fail softly via finalize
    monkeypatch.setattr(
        gv,
        "_finalize",
        lambda **kw: {"status": "ok", "tenant_seen": seen.get("tenant_id"), **kw},
    )

    # After load, code continues with graph ops — stub graph attrs used
    class _G2:
        def get_node(self, *_a, **_k):
            return None

    def _fake_load2(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G2()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load2
    )
    out = asyncio.get_event_loop().run_until_complete(
        gv.sys_graph_validate("demo", operation="consistency", tenant_id="n09-t24")
    )
    assert seen.get("tenant_id") == "n09-t24"
    assert isinstance(out, dict)
