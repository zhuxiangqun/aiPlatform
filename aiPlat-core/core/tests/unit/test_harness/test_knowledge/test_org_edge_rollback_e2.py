"""E2 — roll back one snapshotted merge edge. Not YAML, not unsnapshotted edges."""

from __future__ import annotations

import json

from core.apps.fde.service.k_wave_arbit import (
    apply_ticket,
    decide_ticket,
    propose_ticket,
    rollback_ticket_edge,
    tickets_path,
)
from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore
from core.harness.ontology_engine.graph_index import GraphIndex


def _merged(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    GraphIndex._loaded_instances.clear()
    left = GraphIndex.load("it-ops")
    right = GraphIndex.load("data-gov")
    left.add_entity("L", "left", "Alert")
    right.add_entity("R", "right", "Alert")
    left.add_entity_property("L", "_cross_domain", {"target_id": "old", "target_domain": "data-gov"})
    ticket = propose_ticket(
        left_id="L",
        right_id="R",
        left_domain="it-ops",
        right_domain="data-gov",
        confidence=1.0,
        strategy="exact",
        suggested="merge",
    )
    decide_ticket(ticket["ticket_id"], decision="merge", actor="arbiter")
    applied = apply_ticket(ticket["ticket_id"], actor="arbiter")
    assert applied["ok"] is True
    return ticket["ticket_id"]


def test_rollback_restores_both_sides(tmp_path, monkeypatch):
    def _no_yaml(*_a, **_k):
        raise AssertionError("rollback_proposal")

    monkeypatch.setattr(VersionedOntologyStore, "rollback_proposal", _no_yaml)
    tid = _merged(tmp_path, monkeypatch)
    out = rollback_ticket_edge(tid, role="operator")
    assert out["ok"] is True
    assert out["live_yaml_written"] is False
    assert out["ticket"]["edge_rolled_back"] is True
    left = GraphIndex.load("it-ops").get_node("L").metadata["_cross_domain"]
    assert left["target_id"] == "old"
    assert "_cross_domain" not in (GraphIndex.load("data-gov").get_node("R").metadata or {})
    again = rollback_ticket_edge(tid, role="operator")
    assert again["idempotent"] is True
    blocked = apply_ticket(tid, actor="arbiter")
    assert blocked["reason"] == "already_rolled_back"


def test_missing_snapshot_and_superseded(tmp_path, monkeypatch):
    tid = _merged(tmp_path, monkeypatch)
    GraphIndex.load("it-ops").add_entity_property(
        "L", "_cross_domain", {"target_id": "other", "target_domain": "data-gov"}
    )
    denied = rollback_ticket_edge(tid, role="operator")
    assert denied["reason"] == "edge_superseded"
    assert GraphIndex.load("data-gov").get_node("R").metadata["_cross_domain"]["target_id"] == "L"

    rows = []
    for line in tickets_path().read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("ticket_id") == tid:
                row.pop("edge_before", None)
            rows.append(row)
    tickets_path().write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    missing = rollback_ticket_edge(tid, role="operator")
    assert missing["reason"] == "edge_before_missing"


def test_empty_role_does_not_write(tmp_path, monkeypatch):
    tid = _merged(tmp_path, monkeypatch)
    out = rollback_ticket_edge(tid, role="")
    assert out["reason"] == "identity_missing"
    assert GraphIndex.load("it-ops").get_node("L").metadata["_cross_domain"]["target_id"] == "R"


def test_right_side_failure_restores_left(tmp_path, monkeypatch):
    tid = _merged(tmp_path, monkeypatch)
    real = GraphIndex.set_entity_property

    def _fail_right(self, entity_id, key, value):
        if self.domain_id == "data-gov":
            return False
        return real(self, entity_id, key, value)

    monkeypatch.setattr(GraphIndex, "set_entity_property", _fail_right)
    out = rollback_ticket_edge(tid, role="admin")
    assert out["reason"] == "edge_restore_failed"
    assert GraphIndex.load("it-ops").get_node("L").metadata["_cross_domain"]["target_id"] == "R"
