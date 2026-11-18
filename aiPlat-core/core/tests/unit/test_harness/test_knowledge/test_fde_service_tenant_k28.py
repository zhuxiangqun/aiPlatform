"""N09 K28 — FDE service GraphIndex tenant."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



_FILES = (
    "aiPlat-core/core/apps/fde/service/k_wave_reason.py",
    "aiPlat-core/core/apps/fde/service/abox_connector.py",
    "aiPlat-core/core/apps/fde/service/ontology_pillars.py",
    "aiPlat-core/core/apps/fde/service/rapid_insight_service.py",
    "aiPlat-core/core/apps/fde/service/governance_deepen.py",
    "aiPlat-core/core/apps/fde/service/clarify_dialog.py",
)


def _assert_no_bare_loads(rel: str) -> None:
    text = (_repo_root() / rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_fde_service_sources_wire_tenant():
    for rel in _FILES:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "tenant_id=" in text, rel
        assert (
            "_resolve_graph_tenant" in text or "_ri_graph_tenant" in text
        ), rel
        _assert_no_bare_loads(rel)


def test_ri_graph_tenant_resolves(monkeypatch):
    from core.apps.fde.service import rapid_insight_service as ri

    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t28",
    )
    assert ri._ri_graph_tenant() == "n09-t28"


def test_ontology_pillars_loads_tenant(monkeypatch):
    from core.apps.fde.service import ontology_pillars as op

    seen = {}

    class _G:
        _nodes = {}

        def get_entity_classes(self):
            return []

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.api.core_facade.GraphIndex.load", _fake_load
    )
    monkeypatch.setattr(
        "core.api.core_facade.GraphIndex._loaded_instances",
        {},
        raising=False,
    )
    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t28",
    )
    # Avoid YAML side effects — stub domain path missing
    monkeypatch.setattr(op, "_domain_yaml_path", lambda _d: None)
    out = op.get_ontology_pillars("demo-domain")
    assert isinstance(out, dict)
    assert seen.get("tenant_id") == "n09-t28"
    assert seen.get("domain_id") == "demo-domain"
