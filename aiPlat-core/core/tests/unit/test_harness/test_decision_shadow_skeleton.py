"""Ollaya Phase 1 skeleton: muted decision_shadow (no DomainRouter hook)."""

from __future__ import annotations

import inspect
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.harness.decision_shadow import (
    DecisionShadowConfig,
    load_decision_shadow_config,
    redact_payload,
    reset_shadow_dispatcher_for_tests,
)
from core.harness.decision_shadow.audit import AUDIT_FIELD_WHITELIST
from core.harness.knowledge import domain_router as domain_router_mod


def test_config_defaults_off():
    cfg = load_decision_shadow_config(overlay={})
    assert cfg.enabled is False
    assert cfg.store_raw_text is False
    assert cfg.sample_rate > 0


def test_try_enqueue_disabled_is_noop():
    d = reset_shadow_dispatcher_for_tests(
        DecisionShadowConfig(enabled=False, queue_size=8)
    )
    ok = d.try_enqueue(
        {
            "trace_id": "t1",
            "tier": "t3",
            "domain_id_online": "d1",
            "query_raw": "secret query text",
        }
    )
    assert ok is False
    assert d.queue_depth() == 0
    st = d.status()
    assert st["enabled"] is False
    assert st["classify_hook_wired"] is False
    assert st["drops"]["disabled"] >= 1
    assert st["enqueued"] == 0


def test_redact_strips_raw_by_default():
    rec = redact_payload(
        {"query_raw": "hello", "tier": "t3", "domain_id_online": "x"},
        store_raw_text=False,
    )
    assert "query_raw" not in rec
    assert rec["tier"] == "t3"
    assert "query_hash" in rec
    assert set(rec.keys()) <= (AUDIT_FIELD_WHITELIST | {"query_hash", "query_len"})


def test_enabled_queue_full_drops():
    d = reset_shadow_dispatcher_for_tests(
        DecisionShadowConfig(enabled=True, sample_rate=1.0, queue_size=1)
    )
    assert d.try_enqueue({"trace_id": "a", "query_hash": "h1"}) is True
    assert d.try_enqueue({"trace_id": "b", "query_hash": "h2"}) is False
    assert d.status()["drops"]["queue_full"] >= 1


def test_domain_router_has_no_decision_shadow_import():
    src = Path(inspect.getsourcefile(domain_router_mod)).read_text(encoding="utf-8")
    assert "decision_shadow" not in src


def test_facade_and_diagnostics_status():
    reset_shadow_dispatcher_for_tests(DecisionShadowConfig(enabled=False))
    from core.api.core_facade import decision_shadow_status, decision_shadow_try_enqueue

    snap = decision_shadow_status()
    assert snap["ok"] is True
    assert snap["enabled"] is False
    assert snap["classify_hook_wired"] is False
    assert decision_shadow_try_enqueue({"trace_id": "probe", "query_hash": "h"}) is False

    from core.api.routers import diagnostics as diag

    app = FastAPI()
    app.include_router(diag.router)
    client = TestClient(app)
    resp = client.get("/diagnostics/decision-shadow/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True
    assert body.get("enabled") is False
    assert body.get("classify_hook_wired") is False
    probe = client.post(
        "/diagnostics/decision-shadow/try-enqueue",
        json={"trace_id": "probe2", "query_hash": "h2"},
    )
    assert probe.status_code == 200
    assert probe.json().get("accepted") is False
