"""P1 OS 原生沙箱执行器测试（bubblewrap/seatbelt + 生产收紧）。"""

import pytest

from core.harness.infrastructure.os_sandbox import (
    SandboxMode,
    SandboxRequiredError,
    build_os_sandbox_cmd,
    detect_sandbox_mode,
    is_production_profile,
    sandbox_env_ready,
    sandbox_fail_closed,
)


def _clear_sandbox_env(monkeypatch):
    monkeypatch.delenv("AIPLAT_SANDBOX", raising=False)
    monkeypatch.delenv("AIPLAT_PROFILE", raising=False)
    monkeypatch.delenv("AIPLAT_SANDBOX_FAIL_CLOSED", raising=False)
    monkeypatch.delenv("AIPLAT_SANDBOX_FAIL_OPEN", raising=False)


# ── 模式探测 ──────────────────────────────────────────────────

def test_detect_none_when_not_requested(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    mode = detect_sandbox_mode()
    assert mode.kind == "none"
    assert mode.active is False


def test_detect_bwrap_requested(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_SANDBOX", "bwrap")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    mode = detect_sandbox_mode()
    assert mode.kind == "bwrap"
    assert mode.active is True


def test_detect_bwrap_requested_but_missing(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_SANDBOX", "bwrap")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    mode = detect_sandbox_mode()
    assert mode.kind == "bwrap"
    assert mode.available is False
    assert mode.active is False


def test_seatbelt_detection(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_SANDBOX", "seatbelt")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/sandbox-exec" if name == "sandbox-exec" else None)
    mode = detect_sandbox_mode()
    assert mode.kind == "seatbelt"
    assert mode.active is True


def test_production_auto_enables_when_binary_present(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    mode = detect_sandbox_mode()
    assert mode.enabled is True
    assert mode.available is True
    assert mode.active is True
    assert sandbox_fail_closed() is True


def test_production_enabled_but_missing_binary(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    mode = detect_sandbox_mode()
    assert mode.enabled is True
    assert mode.available is False
    assert mode.active is False


def test_explicit_off_disables(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.setenv("AIPLAT_SANDBOX", "off")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    mode = detect_sandbox_mode()
    assert mode.enabled is False
    assert mode.active is False


# ── 命令包装 ──────────────────────────────────────────────────

def test_fail_open_returns_original_cmd(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    cmd = ["python3", "main.py"]
    wrapped = build_os_sandbox_cmd(cmd, workdir="/tmp/proj")
    assert wrapped == cmd


def test_production_fail_closed_raises(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    with pytest.raises(SandboxRequiredError):
        build_os_sandbox_cmd(["python3", "x"], workdir="/tmp")


def test_production_fail_open_escape_hatch(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.setenv("AIPLAT_SANDBOX_FAIL_OPEN", "true")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    assert sandbox_fail_closed() is False
    cmd = ["python3", "x"]
    assert build_os_sandbox_cmd(cmd, workdir="/tmp") == cmd


def test_bwrap_wraps_command(monkeypatch, tmp_path):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_SANDBOX", "bwrap")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    mode = detect_sandbox_mode()
    workdir = str(tmp_path)
    cmd = ["python3", "main.py"]
    wrapped = build_os_sandbox_cmd(cmd, workdir=workdir, network=False, mode=mode)
    assert wrapped[0] == "bwrap"
    assert "--unshare-net" in wrapped
    assert "--die-with-parent" in wrapped
    assert workdir in wrapped
    assert wrapped[-2:] == ["python3", "main.py"]


def test_bwrap_network_allowed_omits_unshare_net(monkeypatch, tmp_path):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_SANDBOX", "bwrap")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    mode = detect_sandbox_mode()
    wrapped = build_os_sandbox_cmd(["curl", "x"], workdir=str(tmp_path), network=True, mode=mode)
    assert "--unshare-net" not in wrapped


def test_seatbelt_wraps_command(monkeypatch, tmp_path):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_SANDBOX", "seatbelt")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/sandbox-exec" if name == "sandbox-exec" else None)
    mode = detect_sandbox_mode()
    wrapped = build_os_sandbox_cmd(["python3", "x"], workdir=str(tmp_path), mode=mode)
    assert wrapped[0] == "sandbox-exec"
    assert wrapped[1] == "-p"
    assert "(deny default)" in wrapped[2]
    assert str(tmp_path) in wrapped[2]


# ── 诊断 ──────────────────────────────────────────────────────

def test_sandbox_env_ready_shape(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    info = sandbox_env_ready()
    assert info["mode"] == "none"
    assert info["fail_closed"] is False
    assert "profile" in info
    assert "production_tightened" in info


def test_sandbox_env_ready_production(monkeypatch):
    _clear_sandbox_env(monkeypatch)
    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    info = sandbox_env_ready()
    assert info["active"] is True
    assert info["fail_closed"] is True
    assert info["production_tightened"] is True
    assert is_production_profile() is True


def test_mode_enum_values():
    assert SandboxMode("bwrap", True, True).active is True
    assert SandboxMode("bwrap", True, False).active is False
    assert SandboxMode("bwrap", False, True).active is False
