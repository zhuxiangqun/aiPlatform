"""N09 K21 — context_bus / system_health GraphIndex tenant wiring."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



def test_context_bus_source_wires_tenant():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/context_bus.py").read_text(
        encoding="utf-8"
    )
    assert "def _resolve_graph_tenant" in text
    assert "GraphIndex.load(did, tenant_id=tid)" in text
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in text
    assert "GraphIndex.load(\"knowledge-atom\", tenant_id=tid)" in text
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == []


def test_system_health_source_aggregates_tenants():
    text = (_repo_root() / "aiPlat-core/core/harness/evaluation/system_health.py").read_text(encoding="utf-8")
    assert "list_kb_tenant_ids" in text
    assert "audit_all_domains(tenant_id=_tid)" in text
    assert "GraphIndex.load(yf.stem, tenant_id=_tid)" in text
    assert "audit_all_domains()" not in text


def test_resolve_graph_tenant_prefers_params(monkeypatch):
    from core.harness.knowledge import context_bus as cb

    monkeypatch.setattr(
        "core.harness.kernel.execution_context.get_active_request_context",
        lambda: None,
        raising=False,
    )
    assert cb._resolve_graph_tenant({"tenant_id": "n09-t21"}) == "n09-t21"
    assert cb._resolve_graph_tenant({}) == "default"
    assert cb._resolve_graph_tenant(None) == "default"


def test_inject_graph_traversal_loads_tenant(monkeypatch):
    from core.harness.knowledge import context_bus as cb

    seen = {}

    class _G:
        def stats(self):
            return {"node_count": 0, "edge_count": 0}

        def find_by_name(self, _kw):
            return None

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    parts = []
    cb._inject_graph_traversal(parts, "demo", {"tenant_id": "n09-t21", "pain_points": ""})
    assert seen.get("tenant_id") == "n09-t21"
