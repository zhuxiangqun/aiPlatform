"""Phase C3 — DigitalPost governance gate."""

from __future__ import annotations

import json

from core.apps.org.service.org_post import evaluate_post_gate, get_post, list_posts


def test_seed_post_valid():
    pack = get_post("it-ops.alert.pilot")
    assert pack["status"] == "ok"
    post = pack["post"]
    assert post["org_goal_id"] == "goal-it-ops-alert-sla"
    assert "feishu" in post["channel_allowlist"]
    assert post["interface_refs"]
    assert post["sla"]["escalate"] == "hitl"
    assert pack["validation"]["ok"] is True


def test_list_posts_includes_seed():
    out = list_posts()
    assert out["count"] >= 1
    ids = [i["post"]["post_id"] for i in out["items"]]
    assert "it-ops.alert.pilot" in ids


def test_gate_denies_out_of_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    org = tmp_path / "org"
    org.mkdir()
    (org / "pilot_post.json").write_text(
        json.dumps(
            {
                "post_id": "p1",
                "title": "t",
                "version": "0.1.0",
                "enabled": True,
                "domain_id": "it-ops",
                "org_goal_id": "g1",
                "skill_whitelist": ["org_run"],
                "interface_refs": ["it-ops.monitor.fetch"],
                "data_scope": ["it-ops"],
                "channel_allowlist": ["feishu"],
                "sla": {"timeout_sec": 60, "escalate": "hitl"},
                "audit_requirements": ["trace_id"],
            }
        ),
        encoding="utf-8",
    )
    denied = evaluate_post_gate("feishu", domain_id="finance")
    assert denied["ok"] is False
    assert denied["status"] == "data_scope_denied"
    ok = evaluate_post_gate("feishu", domain_id="it-ops")
    assert ok["ok"] is True
    assert ok["org_goal_id"] == "g1"


def test_incomplete_override_invalid(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    org = tmp_path / "org"
    org.mkdir()
    (org / "pilot_post.json").write_text(
        json.dumps(
            {
                "post_id": "thin",
                "title": "thin",
                "version": "0.1.0",
                "enabled": True,
                "domain_id": "it-ops",
                "org_goal_id": "g",
                "channel_allowlist": ["feishu"],
            }
        ),
        encoding="utf-8",
    )
    gate = evaluate_post_gate("feishu")
    assert gate["ok"] is False
    assert gate["status"] == "post_invalid"
