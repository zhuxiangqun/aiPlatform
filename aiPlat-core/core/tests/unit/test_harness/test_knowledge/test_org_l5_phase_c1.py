"""Org Phase C1 — InterfaceSpec (W8) unit tests."""

from __future__ import annotations

from core.apps.org.service.org_interface import (
    assert_action_bound,
    get_interface_spec,
    normalize_interface_spec,
    validate_interface_spec,
)
from core.apps.org.service.org_live_adapter import fetch_live_http, live_io_gates
from core.apps.fde.service.abox_connector import fetch_entity_snapshot


def test_it_ops_seed_interface_spec_valid_disabled():
    pack = get_interface_spec("it-ops")
    assert pack["status"] == "ok"
    spec = pack["spec"]
    val = pack["validation"]
    assert spec["interface_ref"] == "it-ops.monitor.fetch"
    assert spec["adapter"] == "http_json"
    assert spec["enabled"] is False
    assert val["ok"] is True
    assert val["declared"] is False  # empty allowlist
    assert "triage_alert" in spec["bound_action_ids"]
    assert spec["auth"]["type"] == "bearer_env"
    assert spec["auth"]["env"]


def test_validate_rejects_plaintext_secret():
    spec = normalize_interface_spec(
        "it-ops",
        {
            "interface_ref": "it-ops.bad",
            "adapter": "http_json",
            "enabled": False,
            "allowed_hosts": ["sandbox.example.com"],
            "auth": {"type": "bearer_env", "env": "TOK", "token": "plaintext-leak"},
            "timeout_sec": 5,
        },
    )
    val = validate_interface_spec(spec, raw_live={"token": "also-bad"})
    assert val["ok"] is False
    assert any("plaintext" in e for e in val["errors"])


def test_validate_enabled_requires_hosts():
    spec = normalize_interface_spec(
        "it-ops",
        {
            "interface_ref": "it-ops.x",
            "adapter": "http_json",
            "enabled": True,
            "allowed_hosts": [],
            "auth": {"type": "none"},
            "timeout_sec": 5,
        },
    )
    val = validate_interface_spec(spec)
    assert val["ok"] is False
    assert any("allowed_hosts" in e for e in val["errors"])


def test_validate_rejects_non_http_json_adapter():
    spec = normalize_interface_spec(
        "it-ops",
        {
            "interface_ref": "it-ops.sql",
            "adapter": "jdbc_sql",
            "enabled": False,
            "allowed_hosts": ["db.example.com"],
            "auth": {"type": "none"},
            "timeout_sec": 5,
        },
    )
    val = validate_interface_spec(spec)
    assert val["ok"] is False
    assert any("http_json" in e for e in val["errors"])


def test_assert_action_bound_seed():
    ok = assert_action_bound("it-ops", "triage_alert")
    assert ok["allowed"] is True
    bad = assert_action_bound("it-ops", "delete_everything")
    assert bad["allowed"] is False
    assert bad["status"] == "action_not_bound"


def test_live_gates_blocked_when_spec_not_declared(monkeypatch):
    monkeypatch.delenv("AIPLAT_ORG_IO_LIVE_UNLOCK", raising=False)
    gates = live_io_gates("it-ops")
    assert gates["live_io_enabled"] is False
    assert gates["status"] == "blocked"
    assert gates.get("interface_ref") == "it-ops.monitor.fetch"


def test_fetch_live_rejects_unbound_action(monkeypatch):
    import core.apps.org.service.org_field_ops as field_ops
    import core.apps.org.service.org_interface as iface

    monkeypatch.setattr(
        field_ops,
        "evaluate_live_unlock",
        lambda: {"status": "acknowledged", "live_io_enabled": False},
    )

    def _pack(_domain_id="it-ops"):
        live = {
            "interface_ref": "it-ops.test",
            "domain_id": "it-ops",
            "version": "0.1.0",
            "adapter": "http_json",
            "enabled": True,
            "allowed_hosts": ["127.0.0.1"],
            "base_url": "http://127.0.0.1",
            "path_template": "/v1/entities/{entity_id}",
            "timeout_sec": 5,
            "auth": {"type": "none"},
            "bound_action_ids": ["triage_alert"],
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "audit_fields": ["interface_ref"],
        }
        spec = normalize_interface_spec("it-ops", live)
        val = validate_interface_spec(spec, raw_live=live)
        return {"status": "ok", "spec": spec, "validation": val}

    monkeypatch.setattr(iface, "get_interface_spec", _pack)
    monkeypatch.setattr(iface, "load_live_raw", lambda _d: _pack()["spec"])

    out = fetch_live_http("it-ops", "ALT-1", action_id="not_bound_action")
    assert out["status"] == "action_not_bound"


def test_fetch_live_http_via_interface_spec(monkeypatch):
    import core.apps.org.service.org_field_ops as field_ops
    import core.apps.org.service.org_interface as iface
    import core.apps.org.service.org_live_adapter as adapter

    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "live")
    monkeypatch.setattr(
        field_ops,
        "evaluate_live_unlock",
        lambda: {"status": "acknowledged", "live_io_enabled": False},
    )

    live = {
        "interface_ref": "it-ops.test",
        "domain_id": "it-ops",
        "version": "0.1.0",
        "adapter": "http_json",
        "enabled": True,
        "allowed_hosts": ["127.0.0.1"],
        "base_url": "http://127.0.0.1",
        "path_template": "/v1/entities/{entity_id}",
        "timeout_sec": 5,
        "auth": {"type": "none"},
        "bound_action_ids": ["triage_alert"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object", "properties": {"ticket": {"type": "string"}}},
        "audit_fields": ["interface_ref"],
    }

    def _pack(_domain_id="it-ops"):
        spec = normalize_interface_spec("it-ops", live)
        val = validate_interface_spec(spec, raw_live=live)
        assert val["ok"] and val["declared"] and val["enabled"]
        return {"status": "ok", "spec": spec, "validation": val}

    monkeypatch.setattr(iface, "get_interface_spec", _pack)

    class _Resp:
        status = 200
        headers = {"Content-Type": "application/json"}

        def read(self, _n):
            return b'{"ticket":"T-1","state":"open"}'

        def getcode(self):
            return 200

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(adapter, "urlopen", lambda *_a, **_k: _Resp())
    out = fetch_entity_snapshot("it-ops", "ALT-主", purpose="test")
    assert out["status"] == "ok"
    assert out.get("interface_ref") == "it-ops.test"
    assert out.get("payload", {}).get("ticket") == "T-1"
    assert out.get("sandbox_tier") == "customer_http"
