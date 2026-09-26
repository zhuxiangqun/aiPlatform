"""E1 — save _cross_domain before apply. No rollback endpoint."""

from __future__ import annotations

from core.apps.fde.service.k_wave_arbit import apply_ticket, decide_ticket, get_ticket, propose_ticket
from core.harness.ontology_engine.graph_index import GraphIndex


def _approve(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    GraphIndex._loaded_instances.clear()
    ticket = propose_ticket(**kwargs)
    decide_ticket(ticket["ticket_id"], decision="merge", actor="arbiter")
    return ticket["ticket_id"]


def test_apply_stores_previous_cross_domain(tmp_path, monkeypatch):
    calls = []

    def _ok(*_a, **_k):
        calls.append(1)
        return True

    monkeypatch.setattr(
        "core.harness.knowledge_pipeline.resolver.CrossDomainResolver.resolve",
        staticmethod(_ok),
    )
    tid = _approve(
        tmp_path,
        monkeypatch,
        left_id="L",
        right_id="R",
        left_domain="it-ops",
        right_domain="data-gov",
        confidence=0.9,
    )
    left = GraphIndex.load("it-ops")
    left.add_entity("L", "left", "Alert")
    left.add_entity_property("L", "_cross_domain", {"target_id": "old", "target_domain": "data-gov"})

    out = apply_ticket(tid, actor="arbiter")
    assert out["ok"] is True
    assert calls == [1]
    before = out["ticket"]["edge_before"]
    assert before["left"]["target_id"] == "old"
    assert before["right"] is None
    stored = get_ticket(tid)
    assert stored["edge_before"]["left"]["target_id"] == "old"


def test_missing_entity_snapshots_null(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.harness.knowledge_pipeline.resolver.CrossDomainResolver.resolve",
        staticmethod(lambda *_a, **_k: True),
    )
    tid = _approve(
        tmp_path,
        monkeypatch,
        left_id="none-l",
        right_id="none-r",
        left_domain="it-ops",
        right_domain="data-gov",
    )
    out = apply_ticket(tid, actor="arbiter")
    assert out["ok"] is True
    assert out["ticket"]["edge_before"] == {"left": None, "right": None}


def test_capture_failure_does_not_resolve(tmp_path, monkeypatch):
    calls = []

    def _ok(*_a, **_k):
        calls.append(1)
        return True

    monkeypatch.setattr(
        "core.harness.knowledge_pipeline.resolver.CrossDomainResolver.resolve",
        staticmethod(_ok),
    )

    def _boom(*_a, **_k):
        raise RuntimeError("graph down")

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load",
        _boom,
    )
    tid = _approve(
        tmp_path,
        monkeypatch,
        left_id="L2",
        right_id="R2",
        left_domain="it-ops",
        right_domain="data-gov",
    )
    out = apply_ticket(tid, actor="arbiter")
    assert out["ok"] is False
    assert out["reason"] == "edge_before_capture_failed"
    assert calls == []
    stored = get_ticket(tid)
    assert "edge_before" not in stored
    assert not stored.get("edge_written")
