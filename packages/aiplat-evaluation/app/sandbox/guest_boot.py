"""Firecracker guest boot probe (Linux/KVM).

Honesty:
- ``guest_boot=true`` only after a successful ``InstanceStart`` (or an injected
  transport success in unit tests). Dry-run / missing assets stay false.
- Requires ``microvm_guest_boot_authorized()`` (host_ok + GUEST_BOOT=1 + kernel/rootfs).
- Never flips ``process_split_authorized`` or ``sandbox_real_isolation``.
- Never admits live skill tools.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import tempfile
import time
from typing import Any, Callable, Dict, Optional, Protocol


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, unix_path: str, timeout: float = 5.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self._unix_path = unix_path

    def connect(self) -> None:  # noqa: D401 — stdlib override
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._unix_path)
        self.sock = sock


class GuestBootTransport(Protocol):
    def put_json(self, path: str, body: Dict[str, Any]) -> int: ...


class _UnixSocketFirecrackerTransport:
    """Minimal Firecracker HTTP API client over a Unix domain socket."""

    def __init__(self, sock_path: str, timeout: float = 5.0) -> None:
        self._sock_path = sock_path
        self._timeout = timeout

    def put_json(self, path: str, body: Dict[str, Any]) -> int:
        conn = _UnixHTTPConnection(self._sock_path, timeout=self._timeout)
        try:
            payload = json.dumps(body).encode("utf-8")
            conn.request(
                "PUT",
                path,
                body=payload,
                headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
            )
            resp = conn.getresponse()
            # Drain body so connection can close cleanly.
            _ = resp.read()
            return int(resp.status)
        finally:
            conn.close()


TransportFactory = Callable[[str], GuestBootTransport]


def _boot_timeout_s() -> float:
    try:
        return float(os.environ.get("AIPLAT_EVAL_MICROVM_BOOT_TIMEOUT_SEC") or "15")
    except ValueError:
        return 15.0


def _wait_for_socket(path: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if os.path.exists(path):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.2)
                s.connect(path)
                s.close()
                return True
            except OSError:
                pass
        time.sleep(0.05)
    return False


def probe_guest_boot(
    *,
    transport_factory: Optional[TransportFactory] = None,
    popen_factory: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Attempt a short Firecracker guest boot; tear down immediately after start.

    Inject ``transport_factory`` / ``popen_factory`` for unit tests (no real KVM).
    """
    from app.sandbox.microvm import (
        microvm_bin,
        microvm_guest_assets,
        microvm_guest_boot_authorized,
        microvm_status,
    )

    st = microvm_status()
    audit_base: Dict[str, Any] = {
        "backend": "microvm_guest_boot",
        "probe": "guest_boot",
        "guest_boot": False,
        "guest_boot_authorized": bool(st.get("guest_boot_authorized")),
        "microvm_host_ok": st.get("microvm_host_ok"),
        "kvm_available": st.get("kvm_available"),
        "process_split_authorized": False,
        "sandbox_real_isolation": False,
    }
    if not microvm_guest_boot_authorized():
        return {
            "ok": False,
            "stdout": "",
            "stderr": "guest_boot_not_authorized",
            "audit": {
                **audit_base,
                "detail": st.get("microvm_block_reason"),
                "honesty": (
                    "guest_boot requires Linux host_ok + AIPLAT_EVAL_MICROVM_GUEST_BOOT=1 "
                    "+ KERNEL/ROOTFS assets; process_split_authorized stays false"
                ),
            },
        }

    kernel, rootfs = microvm_guest_assets()
    assert kernel and rootfs  # authorized implies assets present
    bin_path = microvm_bin()
    timeout = _boot_timeout_s()
    popen = popen_factory or subprocess.Popen
    factory = transport_factory or (
        lambda sock: _UnixSocketFirecrackerTransport(sock, timeout=min(5.0, timeout))
    )

    tmp = tempfile.mkdtemp(prefix="aiplat-fc-boot-")
    sock_path = os.path.join(tmp, "firecracker.sock")
    log_path = os.path.join(tmp, "fc.log")
    proc: Any = None
    try:
        with open(log_path, "wb") as logf:
            proc = popen(
                [bin_path, "--api-sock", sock_path, "--id", "aiplat-guest-boot-probe"],
                stdout=logf,
                stderr=subprocess.STDOUT,
            )
        if not _wait_for_socket(sock_path, min(5.0, timeout)):
            return {
                "ok": False,
                "stdout": "",
                "stderr": "api_sock_timeout",
                "audit": {**audit_base, "sock": sock_path, "log": log_path},
            }
        transport = factory(sock_path)
        steps: list[tuple[str, int]] = []
        for path, body in (
            (
                "/machine-config",
                {"vcpu_count": 1, "mem_size_mib": 128, "smt": False},
            ),
            (
                "/boot-source",
                {
                    "kernel_image_path": kernel,
                    "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
                },
            ),
            (
                "/drives/rootfs",
                {
                    "drive_id": "rootfs",
                    "path_on_host": rootfs,
                    "is_root_device": True,
                    "is_read_only": True,
                },
            ),
            ("/actions", {"action_type": "InstanceStart"}),
        ):
            status = transport.put_json(path, body)
            steps.append((path, status))
            if status not in (200, 204):
                return {
                    "ok": False,
                    "stdout": "",
                    "stderr": f"api_error:{path}:{status}",
                    "audit": {**audit_base, "steps": steps, "sock": sock_path},
                }
        from app.sandbox.microvm import set_guest_boot_cache

        set_guest_boot_cache(True)
        return {
            "ok": True,
            "stdout": "InstanceStart",
            "stderr": "",
            "audit": {
                **audit_base,
                "guest_boot": True,
                "steps": steps,
                "kernel": kernel,
                "rootfs": rootfs,
                "honesty": (
                    "Firecracker InstanceStart succeeded; short-lived probe only; "
                    "sandbox_real_isolation=false; process_split_authorized=false; "
                    "≠ live skill tools; ≠ staging authorize"
                ),
            },
        }
    except OSError as exc:
        return {
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
            "audit": {**audit_base, "detail": "os_error"},
        }
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        # Best-effort cleanup of sock; leave log for operators if present.
        try:
            if os.path.exists(sock_path):
                os.unlink(sock_path)
        except OSError:
            pass


def _wire_guest_boot() -> Dict[str, Any]:
    """Same-file caller for method_verify."""
    return probe_guest_boot()
