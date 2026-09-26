"""Org L5 Phase 1: sandbox fetch (no live DB)."""

from __future__ import annotations

import os

from core.apps.fde.service.abox_connector import (
    fetch_entity_snapshot,
    preview_entity_write,
)
from core.apps.org.service.org_io import fetch_by_entity, preview_write
from core.harness.ontology_engine.graph_index import GraphIndex


def test_fetch_need_entity():
    out = fetch_entity_snapshot("it-ops", "")
    assert out["status"] == "need_entity"


def test_fetch_live_mode_blocked(monkeypatch):
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "live")
    monkeypatch.delenv("AIPLAT_ORG_IO_LIVE_UNLOCK", raising=False)
    out = fetch_entity_snapshot("it-ops", "ALT-主")
    assert out["status"] == "live_blocked"
    assert out["mode"] == "live"


def test_fetch_deny_mode_blocked(monkeypatch):
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "deny")
    out = fetch_by_entity("it-ops", "ALT-主")
    assert out["status"] == "mode_blocked"


def test_fetch_it_ops_sandbox_overlay(tmp_path, monkeypatch):
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("it-ops")
    g.add_entity("ALT-主", "告警·查询超时", "告警")
    out = fetch_entity_snapshot("it-ops", "ALT-主", purpose="test")
    assert out["status"] == "ok"
    assert out["mode"] == "sandbox"
    assert out["graph"]["class_name"] == "告警"
    assert out["sandbox"].get("source") == "sandbox-monitor"
    assert out["sandbox"].get("severity") == "critical"


def test_fetch_data_gov_thin_slice(tmp_path, monkeypatch):
    """D5: data-gov readonly fetch proves connector is not it-ops-only."""
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("data-gov")
    g.add_entity("ASSET-积分流水", "积分流水资产", "数据资产")
    out = fetch_by_entity("data-gov", "ASSET-积分流水")
    assert out["status"] == "ok"
    assert out["sandbox"].get("source") == "sandbox-catalog"


def test_write_preview_blocked_by_default(monkeypatch):
    monkeypatch.delenv("AIPLAT_ORG_IO_WRITE", raising=False)
    out = preview_write("it-ops", "ALT-主", {"state": "triaged"})
    assert out["applied"] is False
    assert out["status"] == "dry_run_blocked"
    assert out["unlocked"] is False


def test_fetch_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    GraphIndex._loaded_instances.clear()
    GraphIndex.load("it-ops")
    out = fetch_entity_snapshot("it-ops", "NO-SUCH")
    assert out["status"] == "not_found"


def test_live_http_ssrf_blocks_metadata():
    from core.apps.org.service.org_live_adapter import _url_allowed

    ok, reason = _url_allowed("http://169.254.169.254/latest", ["169.254.169.254"])
    assert ok is False
    assert reason == "metadata_blocked"
    ok2, reason2 = _url_allowed("https://evil.test/x", ["sandbox.example.com"])
    assert ok2 is False
    assert reason2 == "host_not_allowlisted"


def test_fetch_live_http_when_gates_open(monkeypatch):
    """Compat: full InterfaceSpec path covered in test_org_l5_phase_c1."""
    from core.apps.org.service.org_interface import get_interface_spec

    pack = get_interface_spec("it-ops")
    assert pack["validation"]["ok"] is True
    assert pack["spec"]["enabled"] is False
    monkeypatch.setenv("AIPLAT_ORG_IO_MODE", "live")
    monkeypatch.delenv("AIPLAT_ORG_IO_LIVE_UNLOCK", raising=False)
    out = fetch_entity_snapshot("it-ops", "ALT-主")
    assert out["status"] == "live_blocked"
