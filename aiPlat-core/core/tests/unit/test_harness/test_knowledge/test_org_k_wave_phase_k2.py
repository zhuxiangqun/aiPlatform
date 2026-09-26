"""Phase K2 — arbitration before CrossDomainResolver.resolve."""

from __future__ import annotations

from core.apps.fde.service.k_wave_arbit import (
    apply_ticket,
    decide_ticket,
    list_tickets,
    propose_ticket,
)


def test_propose_does_not_write_edge(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("resolve must not run on propose")

    monkeypatch.setattr(
        "core.harness.knowledge_pipeline.resolver.CrossDomainResolver.resolve",
        staticmethod(_boom),
    )
    out = propose_ticket(
        view_name="v",
        left_id="a",
        right_id="b",
        left_domain="it-ops",
        right_domain="it-ops",
        confidence=1.0,
        strategy="exact",
        suggested="merge",
        trace_id="trace-k2",
    )
    assert out["ok"] is True
    assert out["status"] == "pending"
    assert out["trace_id"] == "trace-k2"
    assert out["edge_written"] is False
    assert called["n"] == 0
    again = propose_ticket(
        left_id="a",
        right_id="b",
        left_domain="it-ops",
        right_domain="it-ops",
    )
    assert again["idempotent"] is True
    assert again["ticket_id"] == out["ticket_id"]


def test_cross_tenant_auto_reject(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = propose_ticket(
        left_id="a",
        right_id="b",
        left_domain="it-ops",
        right_domain="it-ops",
        left_tenant="t1",
        right_tenant="t2",
    )
    assert out["ok"] is True
    assert out["status"] == "rejected"
    assert out["reason"] == "cross_tenant"


def test_apply_requires_approved_merge(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    writes = []

    def _ok(*args, **kwargs):
        writes.append((args, kwargs))
        return True

    monkeypatch.setattr(
        "core.harness.knowledge_pipeline.resolver.CrossDomainResolver.resolve",
        staticmethod(_ok),
    )
    ticket = propose_ticket(
        left_id="L",
        right_id="R",
        left_domain="it-ops",
        right_domain="data-gov",
        confidence=0.9,
        strategy="fuzzy",
    )
    blocked = apply_ticket(ticket["ticket_id"], actor="x")
    assert blocked["ok"] is False
    assert blocked["reason"] == "not_approved"
    assert writes == []

    decided = decide_ticket(ticket["ticket_id"], decision="merge", actor="arbiter-1")
    assert decided["ok"] is True
    assert decided["ticket"]["status"] == "approved"
    assert decided["ticket"]["arbit_actor"] == "arbiter-1"

    applied = apply_ticket(ticket["ticket_id"], actor="arbiter-1")
    assert applied["ok"] is True
    assert applied["edge_written"] is True
    assert len(writes) == 1

    again = apply_ticket(ticket["ticket_id"], actor="arbiter-1")
    assert again["idempotent"] is True
    assert len(writes) == 1


def test_list_and_reject(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    t = propose_ticket(
        left_id="1",
        right_id="2",
        left_domain="it-ops",
        right_domain="it-ops",
    )
    decide_ticket(t["ticket_id"], decision="reject", actor="a")
    listed = list_tickets(status="rejected")
    assert listed["count"] == 1
    assert listed["items"][0]["ticket_id"] == t["ticket_id"]
