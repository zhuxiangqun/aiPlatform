"""W6: architecture health checks."""
from __future__ import annotations

from core.harness.observability.architecture_health import (
    build_architecture_health_checks,
    build_architecture_health_report,
)


def test_architecture_health_report_shape(monkeypatch):
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_DYNAMIC_ROUTER_ENABLED", raising=False)
    monkeypatch.delenv("AIPLAT_GOAL_AUTO_EXECUTE", raising=False)
    report = build_architecture_health_report()
    assert report["status"] in ("pass", "warn", "fail")
    assert report["summary"]["total"] >= 6
    ids = {c["id"] for c in report["checks"]}
    assert "policy_fail_mode" in ids
    assert "llm_bypass_allowlist" in ids
    assert "retrieval_crag_entry" in ids
    assert "autonomous_default_off" in ids
    assert "multi_agent_default_single" in ids


def test_production_profile_warns_on_open_fail_mode(monkeypatch):
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.setenv("AIPLAT_POLICY_FAIL_MODE", "open")
    monkeypatch.delenv("AIPLAT_POLICY_FAIL_CRITICAL_MODE", raising=False)
    checks = {c["id"]: c for c in build_architecture_health_checks()}
    assert checks["policy_fail_mode"]["status"] in ("warn", "fail")


def test_autonomous_default_off_pass(monkeypatch):
    monkeypatch.delenv("AIPLAT_GOAL_AUTO_EXECUTE", raising=False)
    checks = {c["id"]: c for c in build_architecture_health_checks()}
    assert checks["autonomous_default_off"]["status"] == "pass"


def test_multi_agent_default_single_pass():
    checks = {c["id"]: c for c in build_architecture_health_checks()}
    assert checks["multi_agent_default_single"]["status"] == "pass"
