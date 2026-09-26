"""Phase C4 — usage ledger does not block runs and has no prices."""

from __future__ import annotations

from core.apps.org.service.org_runtime import run_org_goal
from core.apps.org.service.org_usage import append_events, events_from_run, weekly_usage


def test_append_idempotent_and_weekly(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    run = {
        "run_id": "run-1",
        "goal_id": "g",
        "domain_id": "it-ops",
        "week_label": "w1",
        "token_usage": 12,
        "steps": [{"step": "triage_gate"}],
    }
    ev = events_from_run(run, channel="feishu", tenant_id="t1")
    assert all(e.get("billing") is None for e in ev)
    first = append_events(ev)
    second = append_events(ev)
    assert first["written"] == len(ev)
    assert second["written"] == 0
    roll = weekly_usage("it-ops", "w1")
    assert roll["run_count"] == 1
    assert roll["action_count"] == 1
    assert roll["token_total"] == 12
    assert roll["by_channel"]["feishu"] == 1
    assert roll["billing"] is None
    assert "price" not in roll
    other = weekly_usage("it-ops", "w-other")
    assert other["run_count"] == 0
    assert other["token_total"] == 0


def test_ledger_failure_does_not_block_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    import core.apps.org.service.org_usage as usage

    def _boom(*_a, **_k):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(usage, "append_events", _boom)
    monkeypatch.setattr(
        "core.apps.org.service.org_runtime._resolve_goal",
        lambda *_a, **_k: {
            "goal_id": "g",
            "domain_id": "it-ops",
            "status": "active",
            "exception_policy": {"triage_requires_hitl": False, "max_entities_per_run": 1},
            "query_open": "none",
            "steps": ["locate"],
        },
    )
    monkeypatch.setattr(
        "core.apps.fde.service.governance_deepen.locate_via_ontology",
        lambda *_a, **_k: {"status": "ok", "hits": []},
    )
    out = run_org_goal(domain_id="it-ops", dry_actions=False, week_label="w9")
    assert out.get("run_id")
    assert out.get("status") in ("succeeded", "completed_partial", "needs_hitl")
