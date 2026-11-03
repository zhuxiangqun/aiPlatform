"""microVM guest_boot + authorize flag (process_split stays locked)."""
from __future__ import annotations

import platform

import pytest

from app.sandbox.guest_boot import probe_guest_boot
from app.sandbox.microvm import (
    clear_guest_boot_cache,
    guest_boot_cached,
    microvm_guest_boot_authorized,
    microvm_status,
    set_guest_boot_cache,
)


@pytest.fixture(autouse=True)
def _reset_boot_cache():
    clear_guest_boot_cache()
    yield
    clear_guest_boot_cache()


def _linux_host(monkeypatch, tmp_path):
    bin_path = tmp_path / "fake-fc"
    bin_path.write_text("#!/bin/sh\necho firecracker\n", encoding="utf-8")
    bin_path.chmod(0o755)
    kernel = tmp_path / "vmlinux"
    rootfs = tmp_path / "rootfs.ext4"
    kernel.write_bytes(b"K")
    rootfs.write_bytes(b"R")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", str(bin_path))
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_GUEST_BOOT", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_KERNEL", str(kernel))
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ROOTFS", str(rootfs))
    monkeypatch.setattr("app.sandbox.microvm.platform.system", lambda: "linux")
    monkeypatch.setattr("app.sandbox.microvm.os.path.exists", lambda p: p == "/dev/kvm")
    return bin_path, kernel, rootfs


def test_darwin_never_guest_boot_authorized(monkeypatch, tmp_path):
    if platform.system().lower() != "darwin":
        pytest.skip("darwin-only honesty check")
    kernel = tmp_path / "vmlinux"
    rootfs = tmp_path / "rootfs.ext4"
    kernel.write_bytes(b"K")
    rootfs.write_bytes(b"R")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", "/bin/true")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_GUEST_BOOT", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_KERNEL", str(kernel))
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ROOTFS", str(rootfs))
    assert microvm_guest_boot_authorized() is False
    st = microvm_status()
    assert st["guest_boot"] is False
    assert st["process_split_authorized"] is False
    result = probe_guest_boot()
    assert result["ok"] is False
    assert result["stderr"] == "guest_boot_not_authorized"
    assert result["audit"]["guest_boot"] is False


def test_authorize_requires_flag_and_assets(monkeypatch, tmp_path):
    bin_path = tmp_path / "fake-fc"
    bin_path.write_text("#!/bin/sh\necho firecracker\n", encoding="utf-8")
    bin_path.chmod(0o755)
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", str(bin_path))
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS", "1")
    monkeypatch.delenv("AIPLAT_EVAL_MICROVM_GUEST_BOOT", raising=False)
    monkeypatch.delenv("AIPLAT_EVAL_MICROVM_KERNEL", raising=False)
    monkeypatch.delenv("AIPLAT_EVAL_MICROVM_ROOTFS", raising=False)
    monkeypatch.setattr("app.sandbox.microvm.platform.system", lambda: "linux")
    monkeypatch.setattr("app.sandbox.microvm.os.path.exists", lambda p: p == "/dev/kvm")
    assert microvm_guest_boot_authorized() is False
    reason = microvm_status()["microvm_block_reason"]
    assert reason == "linux_track_admit_ready_guest_boot_flag_off"


def test_probe_guest_boot_success_with_injected_transport(monkeypatch, tmp_path):
    _linux_host(monkeypatch, tmp_path)
    assert microvm_guest_boot_authorized() is True
    assert guest_boot_cached() is False

    class _FakeTransport:
        def put_json(self, path, body):
            return 204

    class _FakeProc:
        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    def _fake_popen(*args, **kwargs):
        # Create a fake sock file so wait_for_socket succeeds via connect fail→retry
        # We patch wait instead.
        return _FakeProc()

    monkeypatch.setattr(
        "app.sandbox.guest_boot._wait_for_socket", lambda path, timeout_s: True
    )
    result = probe_guest_boot(
        transport_factory=lambda sock: _FakeTransport(),
        popen_factory=_fake_popen,
    )
    assert result["ok"] is True
    assert result["audit"]["guest_boot"] is True
    assert guest_boot_cached() is True
    st = microvm_status()
    assert st["guest_boot"] is True
    assert st["guest_boot_authorized"] is True
    assert st["process_split_authorized"] is False


def test_probe_denies_without_authorize(monkeypatch, tmp_path):
    bin_path = tmp_path / "fake-fc"
    bin_path.write_text("#!/bin/sh\necho firecracker\n", encoding="utf-8")
    bin_path.chmod(0o755)
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ENABLED", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_BIN", str(bin_path))
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_ADMIT_RUNNERS", "1")
    monkeypatch.setenv("AIPLAT_EVAL_MICROVM_GUEST_BOOT", "0")
    monkeypatch.setattr("app.sandbox.microvm.platform.system", lambda: "linux")
    monkeypatch.setattr("app.sandbox.microvm.os.path.exists", lambda p: p == "/dev/kvm")
    result = probe_guest_boot()
    assert result["ok"] is False
    assert guest_boot_cached() is False


def test_set_guest_boot_cache_helper():
    set_guest_boot_cache(True)
    assert guest_boot_cached() is True
    clear_guest_boot_cache()
    assert guest_boot_cached() is False
