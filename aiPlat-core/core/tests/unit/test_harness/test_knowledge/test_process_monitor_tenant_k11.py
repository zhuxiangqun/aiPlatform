"""N09 K11 — state_changes physical tenant_id + process_monitor isolation."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_state_db(tmp_path, monkeypatch):
    """Point AIPLAT_HOME at a temp dir so state_history uses an isolated DB."""
    home = tmp_path / "aiplat_home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    # Reset lazy connection if already opened
    import core.harness.ontology_engine.state_history as sh

    sh.close_connection()
    yield home
    sh.close_connection()


def test_record_and_monitor_isolate_by_tenant(isolated_state_db):
    from core.harness.ontology_engine import state_history as sh
    from core.harness.knowledge import process_monitor as pm

    sh.record_transition(
        "n09-dom",
        "ent-a",
        "Order",
        "new",
        "open",
        "manual",
        tenant_id="tenant-a",
    )
    sh.record_transition(
        "n09-dom",
        "ent-b",
        "Order",
        "new",
        "closed",
        "manual",
        tenant_id="tenant-b",
    )

    # Schema has physical column
    conn = sh.get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(state_changes)").fetchall()}
    assert "tenant_id" in cols

    a = pm.state_distribution("n09-dom", tenant_id="tenant-a")
    b = pm.state_distribution("n09-dom", tenant_id="tenant-b")
    assert a and all(True for _ in a)
    assert {row["state_name"] for row in a} == {"open"}
    assert {row["state_name"] for row in b} == {"closed"}
    assert pm.state_distribution("n09-dom", tenant_id="tenant-c") == []

    hist_a = sh.get_domain_history("n09-dom", tenant_id="tenant-a")
    assert len(hist_a) == 1
    assert hist_a[0]["entity_name"] == "ent-a"
