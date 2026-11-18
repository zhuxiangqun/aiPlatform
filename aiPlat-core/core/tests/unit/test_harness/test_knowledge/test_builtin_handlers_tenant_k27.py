"""N09 K27 — builtin_handlers GraphIndex tenant."""
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


def test_builtin_handlers_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/ontology_engine/builtin_handlers.py").read_text(encoding="utf-8")
    assert "def _graph_tenant(" in text
    assert "GraphIndex.load(domain_id, tenant_id=_graph_tenant(params))" in text
    assert (
        "GraphIndex.load(source_domain, tenant_id=_graph_tenant(params))" in text
    )
    assert (
        "GraphIndex.load(target_domain, tenant_id=_graph_tenant(params))" in text
    )
    assert text.count("GraphIndex.load(") == 11
    _assert_no_bare_loads(
        "aiPlat-core/core/harness/ontology_engine/builtin_handlers.py"
    )


def test_graph_tenant_prefers_params(monkeypatch):
    from core.harness.ontology_engine import builtin_handlers as bh

    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "ctx-default",
    )
    assert bh._graph_tenant({"tenant_id": "n09-t27"}) == "n09-t27"
    assert bh._graph_tenant({}) == "ctx-default"
    assert bh._graph_tenant(None) == "ctx-default"


def test_approve_diagnosis_loads_tenant(monkeypatch):
    import asyncio
    from core.harness.ontology_engine import builtin_handlers as bh

    seen = {}

    class _G:
        def update_entity_property(self, *a, **k):
            return None

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    out = asyncio.get_event_loop().run_until_complete(
        bh.approve_diagnosis(
            {"id": "e1", "domain_id": "demo"},
            {"tenant_id": "n09-t27", "assigned_engineer": "a"},
            actor="tester",
        )
    )
    assert seen.get("tenant_id") == "n09-t27"
    assert seen.get("domain_id") == "demo"
    assert out.get("new_state") == "in_progress"
