"""Org L5 Phase 3: memory + weekly attribution."""

from __future__ import annotations

from core.apps.org.service.org_kpi import weekly_kpi_report
from core.apps.org.service.org_memory import list_memory, record_run_memory, search_exceptions
from core.apps.org.service.org_runtime import ensure_pilot_goal, resume_run, run_org_goal
from core.harness.ontology_engine.graph_index import GraphIndex


def test_record_and_search_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("it-ops")
    g.add_entity("ALT-主", "告警·查询超时", "告警")

    ensure_pilot_goal("it-ops")
    run = run_org_goal(domain_id="it-ops", dry_actions=True, week_label="w1")
    assert run.get("memory", {}).get("status") == "ok"

    mem = list_memory(domain_id="it-ops", limit=10)
    assert mem["count"] >= 1
    assert any(x.get("run_id") == run["run_id"] for x in mem["items"])

    hits = search_exceptions("hitl", domain_id="it-ops")
    assert hits["count"] >= 1
    assert any("hitl" in str(h.get("exception_reasons")).lower() for h in hits["hits"])


def test_weekly_has_attribution_and_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("it-ops")
    g.add_entity("ALT-主", "告警·查询超时", "告警")

    ensure_pilot_goal("it-ops")
    r1 = run_org_goal(domain_id="it-ops", dry_actions=True, week_label="w1")
    assert r1["status"] == "needs_hitl"

    weekly = weekly_kpi_report("it-ops", week="w1")
    assert weekly["status"] == "ok"
    assert weekly["run_count"] >= 1
    assert "exception_ratio" in weekly["kpis"]
    assert any(x["reason"] == "hitl_required" for x in weekly["failure_attribution_top"])
    assert any(p["run_id"] == r1["run_id"] for p in weekly["pending_hitl"])
    assert weekly["links"]

    resume_run(r1["run_id"], approve=True)
    weekly2 = weekly_kpi_report("it-ops", week="w1")
    assert not any(p["run_id"] == r1["run_id"] for p in weekly2["pending_hitl"])


def test_memory_on_reject(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    GraphIndex._loaded_instances.clear()
    GraphIndex.load("it-ops").add_entity("ALT-主", "告警", "告警")
    ensure_pilot_goal("it-ops")
    r = run_org_goal(domain_id="it-ops", dry_actions=True, week_label="w2")
    out = resume_run(r["run_id"], approve=False)
    assert out["run"]["status"] == "cancelled"
    assert out["run"].get("memory", {}).get("status") == "ok"
    hits = search_exceptions("hitl_rejected", domain_id="it-ops")
    assert hits["count"] >= 1
