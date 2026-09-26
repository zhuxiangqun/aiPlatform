"""Org L5 Phase 4: fleet gate + field ops checklist."""

from __future__ import annotations

from core.apps.fde.service.abox_connector import fetch_entity_snapshot
from core.apps.org.service.org_field_ops import evaluate_live_unlock, field_ops_checklist
from core.apps.org.service.org_fleet import (
    evaluate_fleet_gate,
    request_fleet_or_run,
    set_allow_fleet,
)
from core.apps.org.service.org_runtime import ensure_pilot_goal
from core.harness.ontology_engine.graph_index import GraphIndex


def test_fleet_default_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    ensure_pilot_goal("it-ops")
    gate = evaluate_fleet_gate(domain_id="it-ops")
    assert gate["allowed"] is False
    assert gate["status"] == "blocked"
    assert gate["allow_fleet"] is False


def test_fleet_flag_alone_not_enough_without_required(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    g = ensure_pilot_goal("it-ops")["goal"]
    set_allow_fleet(g["goal_id"], True)
    gate = evaluate_fleet_gate(g["goal_id"], domain_id="it-ops")
    # no project_id → hop check skipped; allow_fleet true + active → allowed
    assert gate["allow_fleet"] is True
    assert gate["allowed"] is True


def test_force_fleet_blocked_when_flag_false(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    GraphIndex._loaded_instances.clear()
    GraphIndex.load("it-ops").add_entity("ALT-主", "告警", "告警")
    ensure_pilot_goal("it-ops")
    out = request_fleet_or_run(domain_id="it-ops", force_fleet=True, week_label="w1")
    assert out["status"] == "fleet_blocked"


def test_live_unlock_blocked_by_default(monkeypatch):
    monkeypatch.delenv("AIPLAT_ORG_IO_LIVE_UNLOCK", raising=False)
    st = evaluate_live_unlock()
    assert st["live_io_enabled"] is False
    assert st["status"] == "blocked"


def test_customer_sandbox_stub_on_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("it-ops")
    g.add_entity("ALT-主", "告警·查询超时", "告警")
    out = fetch_entity_snapshot("it-ops", "ALT-主")
    assert out["status"] == "ok"
    assert out.get("sandbox_tier") == "customer_stub"
    assert out.get("customer_sandbox", {}).get("external_system") == "customer-monitor-stub"


def test_field_ops_includes_customer_stub(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    ensure_pilot_goal("it-ops")
    cl = field_ops_checklist("it-ops")
    assert cl["m4_claim_allowed"] is False
    assert cl["live"]["live_io_enabled"] is False
    ids = {i["id"] for i in cl["items"]}
    assert "runbook" in ids
    assert "fleet_default_deny" in ids
    assert "customer_sandbox_stub" in ids
    stub = next(i for i in cl["items"] if i["id"] == "customer_sandbox_stub")
    assert stub["ok"] is True
    http_item = next(i for i in cl["items"] if i["id"] == "http_json_adapter")
    # C1: InterfaceSpec seed registered + valid; enabled stays false (not outbound-ready)
    assert http_item["ok"] is True
    assert "it-ops.monitor.fetch" in (http_item.get("detail") or "")
    assert "enabled=False" in (http_item.get("detail") or "")
