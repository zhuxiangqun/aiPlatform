"""N09 K20 — ontology completeness/audit/validator load tenant GraphIndex."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")

from types import SimpleNamespace


def test_completeness_audit_validator_source_wire_tenant():
    c = (_repo_root() / "aiPlat-core/core/harness/knowledge/ontology_completeness.py").read_text(encoding="utf-8")
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in c
    # N09 后续：默认租户走 DomainRouter SSOT，禁止字面量 "default"
    assert "tenant_id: str = DomainRouter.default_tenant()" in c

    a = (_repo_root() / "aiPlat-core/core/harness/knowledge/ontology_audit.py").read_text(encoding="utf-8")
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in a
    assert "audit_all_domains(self, *, tenant_id" in a

    v = (_repo_root() / "aiPlat-core/core/harness/knowledge/ontology_validator.py").read_text(encoding="utf-8")
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in v
    assert "tenant_id: str = DomainRouter.default_tenant()" in v


def test_diagnostics_ontology_audit_uses_actor_from_http():
    text = (_repo_root() / "aiPlat-core/core/api/routers/diagnostics.py").read_text(
        encoding="utf-8"
    )
    block = text[
        text.find("def get_ontology_audit") : text.find("def get_audit_trail")
    ]
    assert "actor_from_http(request, None)" in block
    assert "audit_domain(domain_id, tenant_id=tid)" in block
    assert "audit_all_domains(tenant_id=tid)" in block


def test_score_c5_loads_tenant_graph(monkeypatch):
    from core.harness.knowledge import ontology_completeness as ocs

    seen = {}

    class _G:
        def get_entities_by_class(self, _k):
            return []

        def stats(self):
            return {"edge_count": 0}

    def _fake_load(domain_id, tenant_id="default"):
        seen["domain_id"] = domain_id
        seen["tenant_id"] = tenant_id
        return _G()

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load", _fake_load
    )
    domain = SimpleNamespace(classes=[], object_properties=[])
    # empty logic classes → 0.0 early after load
    # add one logic class so load is exercised then covered=0
    domain.classes = [SimpleNamespace(label="C1", name="C1", tier="logic")]
    score = ocs._score_c5("demo", domain, tenant_id="n09-t20")
    assert seen.get("tenant_id") == "n09-t20"
    assert isinstance(score, float)


def test_get_ontology_audit_forwards_identity_tenant(monkeypatch):
    from core.api.routers import diagnostics as diag

    captured = {}

    class _Rep:
        domain_id = "demo"

        def to_dict(self):
            return {"ok": True}

    class _Aud:
        def audit_domain(self, domain_id, *, tenant_id="default"):
            captured["tenant_id"] = tenant_id
            captured["domain_id"] = domain_id
            return _Rep()

        def audit_all_domains(self, *, tenant_id="default"):
            captured["all_tenant"] = tenant_id
            return []

    monkeypatch.setattr(diag, "actor_from_http", lambda _r, _p: {"tenant_id": "n09-aud-20"})
    monkeypatch.setattr(
        "core.harness.knowledge.ontology_audit.OntologyAuditor", _Aud
    )
    out = diag.get_ontology_audit(SimpleNamespace(), domain_id="demo")
    assert out["tenant_id"] == "n09-aud-20"
    assert captured["tenant_id"] == "n09-aud-20"
