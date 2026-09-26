"""Whitelist events may preview in sandbox. They do not start live IO."""

from __future__ import annotations

from core.apps.org.service.org_ingress import list_event_previews, start_event_preview


def test_unknown_event_does_not_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    called = {"n": 0}

    def _dry(*_a, **_k):
        called["n"] += 1
        return {"run_id": "should-not", "status": "needs_hitl"}

    monkeypatch.setattr("core.apps.org.service.org_runtime.run_org_goal", _dry)
    out = start_event_preview(role="admin", domain_id="it-ops", event_type="live.apply")
    assert out["reason"] == "event_not_allowed"
    assert out["live_started"] is False
    assert called["n"] == 0
    assert not (tmp_path / "org" / "event_previews").exists()


def test_allowlisted_event_is_dry_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))

    def _dry(*_a, **kwargs):
        assert kwargs.get("dry_actions") is True
        assert kwargs.get("week_label") == "event_preview"
        return {"run_id": "run-prev", "status": "needs_hitl"}

    monkeypatch.setattr("core.apps.org.service.org_runtime.run_org_goal", _dry)
    denied = start_event_preview(role="", domain_id="it-ops", event_type="signal.preview")
    assert denied["reason"] == "identity_missing"

    out = start_event_preview(role="operator", domain_id="it-ops", event_type="signal.preview")
    assert out["ok"] is True
    assert out["live_started"] is False
    assert out["wrote_live_yaml"] is False
    assert out["notified_channel"] is False
    assert out["second_channel"] is False
    assert out["hitl_status"] == "pending"
    assert out["run_id"] == "run-prev"
    assert out["m4_claim_allowed"] is False
    assert not (tmp_path / "actions").exists()
    listed = list_event_previews()
    assert listed["count"] == 1
    assert listed["items"][0]["live_started"] is False
