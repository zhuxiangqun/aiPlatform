"""microVM prep probe — refuse live tools; never claim real isolation."""
from __future__ import annotations

from app.sandbox.microvm import (
    microvm_available,
    microvm_block_reason,
    microvm_ready,
    microvm_status,
)
from app.sandbox.policy import sandbox_admits, sandbox_backend, sandbox_health
from app.sandbox.skill_policy import skill_suite_is_fixture


def test_microvm_default_not_ready(monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_MICROVM_ENABLED", raising=False)
    monkeypatch.delenv("AIPLAT_EVAL_MICROVM_BIN", raising=False)
    assert microvm_ready() is False
    assert microvm_block_reason() == "microvm_not_enabled"
    st = microvm_status()
    assert st["sandbox_real_isolation"] is False
    assert st["skill_suite_real_tools"] is False
    assert st["process_split_authorized"] is False


def test_microvm_enabled_without_bin_still_blocked(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    missing = tmp_path / "no-such-firecracker"
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", str(missing))
    assert microvm_available() is False
    assert microvm_ready() is False
    reason = microvm_block_reason()
    assert "missing" in reason


def test_microvm_backend_admits_nothing(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "microvm")
    assert sandbox_backend() == "microvm"
    assert sandbox_admits("http_probe") is False
    assert sandbox_admits("cli_probe") is False
    assert sandbox_admits("skill_suite", payload={"mode": "fixture", "cases": []}) is False
    assert sandbox_admits(
        "skill_suite",
        payload={"mode": "live", "tools": ["shell"]},
    ) is False
    health = sandbox_health()
    assert health["sandbox_backend"] == "microvm"
    assert health["sandbox_real_isolation"] is False
    assert health["skill_suite_real_tools"] is False
    assert health["microvm_ready"] is False
    assert health["sandbox_admitted_runners"] == []


def test_live_skill_fixture_policy_still_denies_tools():
    assert skill_suite_is_fixture({"mode": "live", "tools": ["shell"]}) is False
    assert skill_suite_is_fixture({"mode": "fixture", "cases": [{"ok": True}]}) is True
