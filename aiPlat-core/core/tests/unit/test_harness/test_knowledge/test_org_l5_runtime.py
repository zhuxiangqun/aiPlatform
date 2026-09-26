"""Org L5 Phase 2: OrgGoal / OrgRun / HITL resume."""

from __future__ import annotations

from core.apps.org.service.org_runtime import (
    ensure_pilot_goal,
    list_goals,
    list_runs,
    resume_run,
    run_org_goal,
    set_goal_status,
)
from core.harness.ontology_engine.graph_index import GraphIndex


def test_ensure_and_list_goals(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = ensure_pilot_goal("it-ops")
    assert out["status"] in ("installed", "exists")
    assert out["goal"]["goal_id"]
    goals = list_goals("it-ops")
    assert goals["count"] >= 1
    assert goals["goals"][0]["domain_id"] == "it-ops"


def test_set_goal_status(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    g = ensure_pilot_goal("it-ops")["goal"]
    paused = set_goal_status(g["goal_id"], "paused")
    assert paused["status"] == "ok"
    assert paused["goal"]["status"] == "paused"
    active = set_goal_status(g["goal_id"], "active")
    assert active["goal"]["status"] == "active"
    bad = set_goal_status(g["goal_id"], "nope")
    assert bad["status"] == "invalid_status"


def test_dual_week_runs_and_hitl_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("it-ops")
    g.add_entity("ALT-主", "告警·查询超时", "告警")
    g.add_entity("SVC-查询", "服务·查询", "服务")

    ensure_pilot_goal("it-ops")
    r1 = run_org_goal(domain_id="it-ops", dry_actions=True, week_label="w1")
    assert r1["status"] == "needs_hitl"
    assert r1["week_label"] == "w1"
    assert any(s["step"] == "locate" for s in r1["steps"])
    assert any(s["step"] == "fetch" for s in r1["steps"])

    resumed = resume_run(r1["run_id"], approve=True, resolution="ok")
    assert resumed["status"] == "ok"
    assert resumed["run"]["status"] == "succeeded"

    r2 = run_org_goal(domain_id="it-ops", dry_actions=True, week_label="w2")
    assert r2["status"] == "needs_hitl"
    assert r2["run_id"] != r1["run_id"]

    runs = list_runs(r1["goal_id"], limit=10)
    assert runs["count"] >= 2

    rejected = resume_run(r2["run_id"], approve=False)
    assert rejected["run"]["status"] == "cancelled"


def test_paused_goal_not_runnable(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    g = ensure_pilot_goal("it-ops")["goal"]
    set_goal_status(g["goal_id"], "paused")
    out = run_org_goal(g["goal_id"], domain_id="it-ops")
    assert out["status"] == "goal_not_runnable"
