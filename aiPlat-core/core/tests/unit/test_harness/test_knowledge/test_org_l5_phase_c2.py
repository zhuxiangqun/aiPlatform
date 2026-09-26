"""Phase C2 — Feishu ingress: signature, identity, confirm, idempotency."""

from __future__ import annotations

import hashlib
import json
import time

from core.apps.org.service.org_ingress import (
    build_dispatch_evidence,
    ingest_feishu_event,
    process_channel_message,
    verify_lark_signature,
)


def _map(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    org = tmp_path / "org"
    org.mkdir()
    (org / "channel_identity.json").write_text(
        json.dumps({"feishu": {"ou_1": {"tenant_id": "t1", "actor_id": "a1"}}}),
        encoding="utf-8",
    )


def test_signature_and_replay(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch)
    body = b'{"event":{}}'
    key = "k"
    ts = str(int(time.time()))
    nonce = "n1"
    sig = hashlib.sha256((ts + nonce + key).encode() + body).hexdigest()
    ok = verify_lark_signature(ts, nonce, body, sig, encrypt_key=key)
    assert ok["ok"] is True
    again = verify_lark_signature(ts, nonce, body, sig, encrypt_key=key)
    assert again["ok"] is False
    assert again["reason"] == "nonce_replay"


def test_unmapped_and_wrong_channel(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch)
    bad = process_channel_message(
        channel="feishu", message_id="m1", chat_id="c1", user_id="ou_unknown", text="hi"
    )
    assert bad["status"] == "identity_unmapped"
    other = process_channel_message(
        channel="wecom", message_id="m2", chat_id="c1", user_id="ou_1", text="hi"
    )
    assert other["status"] == "channel_not_allowed"


def test_confirm_gate_then_run_with_dispatch(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch)
    import core.apps.org.service.org_runtime as rt

    monkeypatch.setattr(
        rt,
        "run_org_goal",
        lambda **_k: {
            "status": "needs_hitl",
            "run_id": "run-c2",
            "steps": [{"step": "locate", "hit_count": 2}],
        },
    )
    first = process_channel_message(
        channel="lark", message_id="m-a", chat_id="chat1", user_id="ou_1", text="查告警"
    )
    assert first["status"] == "needs_confirm"
    assert "run_id" not in first or not first.get("run_id")

    second = process_channel_message(
        channel="feishu",
        message_id="m-b",
        chat_id="chat1",
        user_id="ou_1",
        text="确认",
    )
    assert second["status"] == "ok"
    assert second["run_id"] == "run-c2"
    assert second["trace_id"] == "run-c2"
    d = second["dispatch"]
    for key in ("object", "action", "interface", "skill", "policy_gate"):
        assert key in d
    st = json.loads((tmp_path / "org" / "ingress_state.json").read_text(encoding="utf-8"))
    assert st["sessions"]["feishu:chat1"] == "run-c2"


def test_cancel_and_idempotent(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch)
    out = process_channel_message(
        channel="feishu", message_id="m-c", chat_id="chat1", user_id="ou_1", action="cancel"
    )
    assert out["status"] == "cancelled"
    again = process_channel_message(
        channel="feishu", message_id="m-c", chat_id="chat1", user_id="ou_1", action="cancel"
    )
    assert again.get("idempotent") is True


def test_ingest_rejects_unsigned(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch)
    monkeypatch.delenv("AIPLAT_FEISHU_ENCRYPT_KEY", raising=False)
    out = ingest_feishu_event({"event": {}}, headers={}, raw_body=b"{}")
    assert out["status"] == "ingress_unconfigured"
    assert out["http_status"] == 503


def test_post_denies_channel_when_allowlist_empty(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch)
    (tmp_path / "org" / "pilot_post.json").write_text(
        json.dumps({"post_id": "p", "enabled": True, "channel_allowlist": []}),
        encoding="utf-8",
    )
    out = process_channel_message(
        channel="feishu", message_id="m-p", chat_id="c1", user_id="ou_1", text="hi"
    )
    assert out["status"] == "post_channel_denied"


def test_dispatch_evidence_shape():
    ev = build_dispatch_evidence("it-ops", {"run_id": "run-x", "status": "needs_hitl", "steps": []})
    assert ev["trace_id"] == "run-x"
    assert ev["skill"]["id"] == "org_run"
    assert "interface_ref" in ev["interface"]
