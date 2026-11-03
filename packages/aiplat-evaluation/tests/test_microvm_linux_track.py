"""microVM Linux/KVM track v1 — admit policy + host allowlist (guest_boot deferred)."""
from __future__ import annotations

import platform

import pytest

from app.sandbox.microvm import (
    kvm_available,
    microvm_can_admit_runners,
    microvm_host_ok,
    microvm_ready,
    microvm_status,
)
from app.sandbox.microvm_exec import run_allowlisted_cli
from app.sandbox.policy import sandbox_admits, sandbox_backend, sandbox_health
from app.sandbox.security_policy import security_redteam_is_fixture


def test_darwin_never_host_ok(monkeypatch):
    if platform.system().lower() != "darwin":
        pytest.skip("darwin-only honesty check")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS", "1")
    # Even with a fake executable path that exists, no KVM on Darwin.
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", "/bin/true")
    assert kvm_available() is False
    assert microvm_host_ok() is False
    assert microvm_can_admit_runners() is False
    st = microvm_status()
    assert st["eligible_on_darwin"] is False
    assert st["guest_boot"] is False


def test_admit_requires_flag_even_when_ready(monkeypatch, tmp_path):
    bin_path = tmp_path / "fake-fc"
    bin_path.write_text("#!/bin/sh\necho firecracker\n", encoding="utf-8")
    bin_path.chmod(0o755)
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", str(bin_path))
    monkeypatch.delenv("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS", raising=False)
    monkeypatch.setattr(
        "app.sandbox.microvm.platform.system", lambda: "linux"
    )
    monkeypatch.setattr("app.sandbox.microvm.os.path.exists", lambda p: p == "/dev/kvm")
    assert microvm_ready() is True
    assert microvm_host_ok() is True
    assert microvm_can_admit_runners() is False
    reason = microvm_status()["microvm_block_reason"]
    assert reason == "host_ok_admit_runners_flag_off"


def test_linux_track_admits_non_live_when_host_ok(monkeypatch, tmp_path):
    bin_path = tmp_path / "fake-fc"
    bin_path.write_text("#!/bin/sh\necho firecracker\n", encoding="utf-8")
    bin_path.chmod(0o755)
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "microvm")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", str(bin_path))
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS", "1")
    monkeypatch.setattr(
        "app.sandbox.microvm.platform.system", lambda: "linux"
    )
    monkeypatch.setattr("app.sandbox.microvm.os.path.exists", lambda p: p == "/dev/kvm")
    assert sandbox_backend() == "microvm"
    assert microvm_can_admit_runners() is True
    assert sandbox_admits("http_probe") is True
    assert sandbox_admits("cli_probe") is True
    assert sandbox_admits(
        "skill_suite", payload={"mode": "fixture", "cases": [{"ok": True}]}
    ) is True
    assert sandbox_admits(
        "skill_suite", payload={"mode": "live", "tools": ["shell"]}
    ) is False
    assert sandbox_admits(
        "security_redteam",
        payload={"mode": "fixture", "cases": []},
    ) is True
    # live_llm must not admit under microvm track v1
    assert sandbox_admits(
        "security_redteam",
        payload={"mode": "live_llm", "attacks": []},
    ) is False
    health = sandbox_health()
    assert health["sandbox_isolation"] == "microvm_linux_track"
    assert health["guest_boot"] is False
    assert "cli_probe" in health["sandbox_admitted_runners"]
    assert "security_redteam(fixture)" in health["sandbox_admitted_runners"]
    assert health["security_live_attacks"] is False


def test_run_allowlisted_cli_under_admit(monkeypatch, tmp_path):
    bin_path = tmp_path / "fake-fc"
    bin_path.write_text("#!/bin/sh\necho firecracker\n", encoding="utf-8")
    bin_path.chmod(0o755)
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", str(bin_path))
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS", "1")
    monkeypatch.setattr(
        "app.sandbox.microvm.platform.system", lambda: "linux"
    )
    monkeypatch.setattr("app.sandbox.microvm.os.path.exists", lambda p: p == "/dev/kvm")
    result = run_allowlisted_cli(["true"])
    assert result["ok"] is True
    assert result["audit"]["guest_boot"] is False
    assert result["audit"]["backend"] == "microvm_track"
    denied = run_allowlisted_cli(["curl", "http://evil"])
    assert denied["ok"] is False


def test_security_fixture_helper():
    assert security_redteam_is_fixture({"mode": "fixture"}) is True
    assert security_redteam_is_fixture({"mode": "live_llm"}) is False


def test_sandbox_probe_wrap_uses_microvm_path(monkeypatch, tmp_path):
    from app.sandbox.microvm_exec import run_sandbox_probe_wrap

    bin_path = tmp_path / "fake-fc"
    bin_path.write_text("#!/bin/sh\necho firecracker\n", encoding="utf-8")
    bin_path.chmod(0o755)
    monkeypatch.setenv("AIPLAT_EVAL_SANDBOX_BACKEND", "microvm")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", str(bin_path))
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS", "1")
    monkeypatch.setattr(
        "app.sandbox.microvm.platform.system", lambda: "linux"
    )
    monkeypatch.setattr("app.sandbox.microvm.os.path.exists", lambda p: p == "/dev/kvm")
    wrap = run_sandbox_probe_wrap()
    assert wrap["ok"] is True
    assert wrap["audit"]["backend"] == "microvm_track"
    assert wrap["audit"]["guest_boot"] is False
