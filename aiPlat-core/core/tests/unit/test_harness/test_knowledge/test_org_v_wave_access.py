"""V2 — console run is one post decision. Ingress is unchanged."""

from __future__ import annotations

from core.apps.org.service.org_ingress import ingress_status
from core.apps.org.service.org_post import authorize_console_run


def test_viewer_cannot_start(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = authorize_console_run(role="viewer", domain_id="it-ops", goal_id="goal-it-ops-alert-sla")
    assert out["ok"] is False
    assert out["reason"] == "role_denied"


def test_empty_role_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = authorize_console_run(role="", domain_id="it-ops", goal_id="goal-it-ops-alert-sla")
    assert out["status"] == "role_denied"


def test_business_matches_post(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = authorize_console_run(role="business", domain_id="it-ops", goal_id="goal-it-ops-alert-sla")
    assert out["ok"] is True
    assert out["post_id"] == "it-ops.alert.pilot"


def test_other_goal_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    out = authorize_console_run(role="admin", domain_id="it-ops", goal_id="goal-other")
    assert out["ok"] is False
    assert out["status"] == "goal_not_on_post"


def test_channel_status_comes_from_api(monkeypatch):
    monkeypatch.delenv("AIPLAT_WECOM_WEBHOOK", raising=False)
    status = ingress_status()
    assert [row["id"] for row in status["inbound"]] == ["feishu"]
    assert status["outbound_only"][0]["id"] == "wecom"
    assert status["outbound_only"][0]["configured"] is False
    assert status["second_channel"] is False
