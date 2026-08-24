"""P1 OS 原生沙箱执行器测试（bubblewrap/seatbelt 可选包装器）。"""

import pytest

from core.harness.infrastructure.os_sandbox import (
    SandboxMode,
    build_os_sandbox_cmd,
    detect_sandbox_mode,
    sandbox_env_ready,
)


# ── 模式探测 ──────────────────────────────────────────────────

def test_detect_none_when_not_requested(monkeypatch):
    monkeypatch.delenv("AIPLAT_SANDBOX", raising=False)
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    mode = detect_sandbox_mode()
    assert mode.kind == "none"
    assert mode.active is False


def test_detect_bwrap_requested(monkeypatch):
    monkeypatch.setenv("AIPLAT_SANDBOX", "bwrap")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    mode = detect_sandbox_mode()
    assert mode.kind == "bwrap"
    assert mode.active is True


def test_detect_bwrap_requested_but_missing(monkeypatch):
    monkeypatch.setenv("AIPLAT_SANDBOX", "bwrap")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    mode = detect_sandbox_mode()
    assert mode.kind == "bwrap"
    assert mode.available is False
    assert mode.active is False  # 无二进制 → 不激活（fail-open）


def test_seatbelt_detection(monkeypatch):
    monkeypatch.setenv("AIPLAT_SANDBOX", "seatbelt")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/sandbox-exec" if name == "sandbox-exec" else None)
    mode = detect_sandbox_mode()
    assert mode.kind == "seatbelt"
    assert mode.active is True


# ── 命令包装 ──────────────────────────────────────────────────

def test_fail_open_returns_original_cmd(monkeypatch):
    monkeypatch.delenv("AIPLAT_SANDBOX", raising=False)
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    cmd = ["python3", "main.py"]
    wrapped = build_os_sandbox_cmd(cmd, workdir="/tmp/proj")
    assert wrapped == cmd  # 无沙箱 → 原命令


def test_bwrap_wraps_command(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_SANDBOX", "bwrap")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    mode = detect_sandbox_mode()
    workdir = str(tmp_path)
    cmd = ["python3", "main.py"]
    wrapped = build_os_sandbox_cmd(cmd, workdir=workdir, network=False, mode=mode)
    assert wrapped[0] == "bwrap"
    assert "--unshare-net" in wrapped  # 默认隔离网络
    assert "--die-with-parent" in wrapped
    assert workdir in wrapped  # 工作区可写
    # 原命令在尾部
    assert wrapped[-2:] == ["python3", "main.py"]


def test_bwrap_network_allowed_omits_unshare_net(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_SANDBOX", "bwrap")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    mode = detect_sandbox_mode()
    wrapped = build_os_sandbox_cmd(["curl", "x"], workdir=str(tmp_path), network=True, mode=mode)
    assert "--unshare-net" not in wrapped


def test_seatbelt_wraps_command(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_SANDBOX", "seatbelt")
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: "/usr/bin/sandbox-exec" if name == "sandbox-exec" else None)
    mode = detect_sandbox_mode()
    wrapped = build_os_sandbox_cmd(["python3", "x"], workdir=str(tmp_path), mode=mode)
    assert wrapped[0] == "sandbox-exec"
    assert wrapped[1] == "-p"
    assert "(deny default)" in wrapped[2]
    assert str(tmp_path) in wrapped[2]  # 工作区可写


# ── 诊断 ──────────────────────────────────────────────────────

def test_sandbox_env_ready_shape(monkeypatch):
    monkeypatch.delenv("AIPLAT_SANDBOX", raising=False)
    monkeypatch.setattr("core.harness.infrastructure.os_sandbox.shutil.which",
                       lambda name: None)
    info = sandbox_env_ready()
    assert set(info.keys()) == {"mode", "available", "enabled", "active", "env"}
    assert info["mode"] == "none"


def test_mode_enum_values():
    assert SandboxMode("bwrap", True, True).active is True
    assert SandboxMode("bwrap", True, False).active is False
    assert SandboxMode("bwrap", False, True).active is False
