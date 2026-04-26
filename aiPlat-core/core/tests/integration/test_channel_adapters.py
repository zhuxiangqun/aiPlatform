import hashlib
import hmac
import importlib
import json
import time

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_webhook_channel_adapter_runs_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")

    import core.server as server

    importlib.reload(server)

    hdr = {"X-AIPLAT-TENANT-ID": "t_demo", "X-AIPLAT-ACTOR-ID": "admin", "X-AIPLAT-ACTOR-ROLE": "admin"}
    with TestClient(server.app) as client:
        r = client.post(
            "/api/core/channels/webhook/event",
            headers=hdr,
            json={"kind": "agent", "target_id": "react_agent", "payload": {"input": {"task": "hi"}, "context": {"tenant_id": "t_demo"}}},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("run_id")


@pytest.mark.integration
def test_slack_channel_adapter_verifies_and_accepts_challenge(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_EXECUTION_DB_PATH", str(tmp_path / "exec.sqlite3"))
    monkeypatch.setenv("AIPLAT_RBAC_MODE", "disabled")
    monkeypatch.setenv("AIPLAT_SLACK_SIGNING_SECRET", "sec_test")

    import core.server as server

    importlib.reload(server)

    body = {"type": "url_verification", "challenge": "abc123"}
    raw = json.dumps(body).encode("utf-8")
    ts = str(int(time.time()))
    base = f"v0:{ts}:{raw.decode('utf-8')}".encode("utf-8")
    sig = "v0=" + hmac.new(b"sec_test", base, hashlib.sha256).hexdigest()

    hdr = {
        "X-AIPLAT-TENANT-ID": "t_demo",
        "X-AIPLAT-ACTOR-ID": "admin",
        "X-AIPLAT-ACTOR-ROLE": "admin",
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": sig,
        "Content-Type": "application/json",
    }
    with TestClient(server.app) as client:
        r = client.post("/api/core/channels/slack/event", headers=hdr, content=raw)
        assert r.status_code == 200, r.text
        assert r.json().get("challenge") == "abc123"

