"""H4 — queue auto-pass is on in sandbox and never writes live YAML."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.apps.fde.service.k_wave_arbit import propose_ticket
from core.apps.fde.service.k_wave_signal import live_yaml_hash
from core.apps.org.service.org_auto_pass import (
    h4_auto_audit,
    h4_rules_view,
    load_rules,
    rules_path,
    run_h4_auto_pass,
)


def _enable(tmp_path: Path, **extra) -> None:
    rules = {
        "enabled": True,
        "sandbox_only": True,
        "confidence_min": 0.95,
        "domains": ["it-ops"],
        "exact_strategies": ["exact"],
        "daily_auto_rate_max": 0.2,
        "min_sample": 5,
    }
    rules.update(extra)
    path = tmp_path / "org" / "approval_rules.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(rules, allow_unicode=True), encoding="utf-8")


@pytest.mark.asyncio
async def test_h4_sandbox_switch_on_no_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "sandbox")
    view = h4_rules_view(role="admin")
    assert view["ok"] is True
    assert view["enabled"] is True
    assert view["called_apply"] is False
    out = await run_h4_auto_pass(role="admin", domain_id="it-ops")
    assert out["ok"] is True
    assert out["called_apply"] is False
    assert out["yaml_unchanged"] is True
    assert out["passed"] == []


@pytest.mark.asyncio
async def test_h4_live_switch_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "live")
    view = h4_rules_view(role="admin")
    assert view["enabled"] is False
    _enable(tmp_path)
    out = await run_h4_auto_pass(role="admin", domain_id="it-ops")
    assert out["ok"] is False
    assert out["reason"] == "live_io_forbidden"
    assert out["called_apply"] is False
    assert out.get("auto_applied_shadow") is False
    after = h4_rules_view(role="admin")
    assert after["live_refused_today"] >= 1
    assert after["live_auto_pass_rate"] == 0.0
    assert after["auto_applied_shadow"] is False
    assert after["io_mode"] == "live"


def test_sandbox_live_delta_hides_live_rate_without_attempts(tmp_path, monkeypatch):
    from core.apps.org.service.org_auto_pass import sandbox_live_delta

    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "sandbox")
    blank = sandbox_live_delta({"auto": 0, "skip": 0, "live_refused": 0})
    assert blank["sandbox_pass_rate"] is None
    assert blank["live_auto_pass_rate"] is None
    assert blank["auto_applied_shadow"] is False
    rated = sandbox_live_delta({"auto": 1, "skip": 1, "live_refused": 2})
    assert rated["sandbox_pass_rate"] == 0.5
    assert rated["live_auto_pass_rate"] == 0.0
    assert rated["live_refused_today"] == 2


@pytest.mark.asyncio
async def test_h4_auto_pass_decide_only_no_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "sandbox")
    _enable(tmp_path)
    (tmp_path / "ontologies").mkdir(parents=True, exist_ok=True)
    yaml_path = tmp_path / "ontologies" / "it-ops.yaml"
    yaml_path.write_text("domain_id: it-ops\nclasses: {}\n", encoding="utf-8")
    before = live_yaml_hash("it-ops")

    propose_ticket(
        left_id="svc-a",
        right_id="svc-b",
        left_domain="it-ops",
        right_domain="it-ops",
        confidence=0.99,
        strategy="exact",
        suggested="merge",
        trace_id="h4-trace",
    )
    # cross-domain must be skipped
    propose_ticket(
        left_id="x",
        right_id="y",
        left_domain="it-ops",
        right_domain="data-gov",
        confidence=0.99,
        strategy="exact",
        suggested="merge",
        trace_id="h4-cross",
    )

    out = await run_h4_auto_pass(role="admin", domain_id="it-ops")
    assert out["ok"] is True
    assert out["called_apply"] is False
    assert out["yaml_unchanged"] is True
    assert live_yaml_hash("it-ops") == before
    kinds = {p["kind"] for p in out["passed"]}
    assert "arbitration" in kinds
    assert any(s["reason"] == "cross_domain" for s in out["skipped"])


@pytest.mark.asyncio
async def test_h4_audit_admin_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    denied = h4_auto_audit(role="operator")
    assert denied["ok"] is False
    assert denied["reason"] == "audit_forbidden"
    ok = h4_auto_audit(role="admin")
    assert ok["ok"] is True


@pytest.mark.asyncio
async def test_h4_circuit_opens_on_high_auto_rate(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "sandbox")
    _enable(tmp_path, daily_auto_rate_max=0.2, min_sample=3)
    # seed audit: 3 auto, 0 skip → rate 100%
    audit = tmp_path / "org" / "h4_audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    import json
    import time

    day = time.strftime("%Y-%m-%d", time.localtime())
    with audit.open("w", encoding="utf-8") as fh:
        for i in range(3):
            fh.write(
                json.dumps(
                    {"event": "auto_pass", "kind": "arbitration", "id": f"t{i}", "day": day}
                )
                + "\n"
            )

    out = await run_h4_auto_pass(role="admin", domain_id="it-ops")
    assert out["ok"] is False
    assert out["reason"] == "circuit_open"
    assert load_rules()["enabled"] is False
    assert rules_path().is_file()
