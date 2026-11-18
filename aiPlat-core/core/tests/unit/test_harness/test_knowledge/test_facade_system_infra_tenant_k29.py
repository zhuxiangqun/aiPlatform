"""N09 K29 — core_facade / system / eval / infra GraphIndex tenant."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


_FILES = (
    "aiPlat-core/core/api/core_facade.py",
    "aiPlat-core/core/api/routers/system.py",
    "aiPlat-core/core/api/routers/wiki_ontology_domains.py",
    "aiPlat-core/core/api/routers/diagnostics_capability.py",
    "aiPlat-core/core/harness/evaluation/constraint_validator.py",
    "aiPlat-core/core/harness/infrastructure/dynamic_mapper.py",
    "aiPlat-core/core/harness/infrastructure/rule_validator.py",
    "aiPlat-core/core/harness/infrastructure/gates/semantic_gate.py",
)


def _assert_no_bare_loads(rel: str) -> None:
    text = (_repo_root() / rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_k29_sources_wire_tenant():
    for rel in _FILES:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "tenant_id" in text, rel
        _assert_no_bare_loads(rel)


def test_rule_validator_init_resolves_tenant(monkeypatch):
    from core.harness.infrastructure import rule_validator as rv

    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t29",
    )
    monkeypatch.setattr(
        rv.RuleValidator,
        "_load_rules",
        lambda self: {},
    )
    v = rv.RuleValidator("demo-domain")
    assert v._tenant_id == "n09-t29"


def test_semantic_gate_loads_tenant(monkeypatch):
    from core.harness.infrastructure.gates import semantic_gate as sg

    seen = {}

    class _G:
        _nodes = {}

        def find_by_name(self, *_a, **_k):
            return None

        def get_node(self, *_a, **_k):
            return None

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    monkeypatch.setattr(
        "core.harness.knowledge.context_bus._resolve_graph_tenant",
        lambda params=None: "n09-t29",
    )
    gate = sg.SemanticGate(mode="warn")
    gate._verify_entities({"entities": []}, "demo-domain")
    assert seen.get("tenant_id") == "n09-t29"
    assert seen.get("domain_id") == "demo-domain"
