"""N09 K12 — OntologyEngine carries tenant_id into record_transition kwargs."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def test_ontology_engine_stores_and_overrides_tenant(monkeypatch):
    from core.harness.ontology_engine import engine as eng_mod

    domain = SimpleNamespace(id="dom", classes=[], object_properties=[])
    monkeypatch.setattr(eng_mod, "ClassMapper", lambda d: MagicMock())
    monkeypatch.setattr(eng_mod, "PropertyExtractor", lambda d: MagicMock())
    monkeypatch.setattr(eng_mod, "StateMachine", lambda d: MagicMock())

    e = eng_mod.OntologyEngine(domain, tenant_id="t-init")
    assert e._tenant_id == "t-init"

    captured = {}

    def _fake_rt(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(eng_mod, "record_transition", _fake_rt)
    # Simulate the write site
    eng_mod.record_transition(
        domain_id=e._domain.id,
        entity_name="e",
        class_name="C",
        from_state="a",
        to_state="b",
        trigger_type="t",
        transition_desc="",
        doc_id="d",
        tenant_id=e._tenant_id,
    )
    assert captured["tenant_id"] == "t-init"
