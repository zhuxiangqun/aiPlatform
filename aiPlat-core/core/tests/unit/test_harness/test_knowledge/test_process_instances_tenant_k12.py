"""N09 K12 — process_instances physical tenant_id + read isolation."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "aiplat_home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    # Reset state_history singleton between tests
    import core.harness.ontology_engine.state_history as sh

    sh.close_connection()
    yield home
    sh.close_connection()


def test_process_instances_isolate_by_tenant(isolated_home):
    from core.harness.knowledge import process_orchestrator as po
    from core.harness.ontology_engine.state_history import record_transition, close_connection
    from core.harness.ontology_engine.engine import OntologyEngine
    from core.harness.knowledge.ontology_loader import OntologyDomain

    # start two tenants
    po.start_process("p1", "dom", "e1", {"steps": []}, tenant_id="t-a")
    po.start_process("p1", "dom", "e2", {"steps": []}, tenant_id="t-b")

    a = po.get_process_status("dom", tenant_id="t-a")
    b = po.get_process_status("dom", tenant_id="t-b")
    assert len(a) == 1 and a[0]["starter_entity"] == "e1"
    assert len(b) == 1 and b[0]["starter_entity"] == "e2"
    assert po.get_process_status("dom", tenant_id="t-c") == []

    ba = po.get_bottlenecks("dom", tenant_id="t-a")
    assert len(ba) == 1 and ba[0]["starter_entity"] == "e1"

    # Engine record_transition uses tenant_id
    close_connection()
    # Minimal domain stub via OntologyEngine requires real domain YAML — test record path via
    # monkeypatch-free: call record_transition with tenant as engine would
    record_transition(
        "dom", "ent", "Cls", "s0", "s1", "manual", tenant_id="t-a"
    )
    from core.harness.knowledge.process_monitor import state_distribution

    dist_a = state_distribution("dom", tenant_id="t-a")
    dist_b = state_distribution("dom", tenant_id="t-b")
    assert any(d.get("state_name") == "s1" for d in dist_a)
    assert dist_b == []
