"""SEC-P4: Linux microVM probed path (guest_sim → isolation_probed)."""
from __future__ import annotations

import os

import pytest

from core.apps.eval.service.isolation_t12 import (
    ISOLATION_ADMITTED,
    ISOLATION_COVERED,
    ISOLATION_PROBED,
    ISOLATION_UNKNOWN,
)
from core.apps.eval.service.security_t12_p4 import (
    MODE_GUEST_LIVE,
    MODE_GUEST_SIM,
    SecurityT12P4Error,
    run_linux_microvm_probes,
    security_sec_p4_status,
)

_LINUX_ADMIT = {
    "os": "linux",
    "linux": True,
    "kvm_device": True,
    "host_ok": True,
    "admit_ready": True,
    "microvm_covered": False,
    "process_split_authorized": False,
}

_DARWIN_ADMIT = {
    "os": "darwin",
    "linux": False,
    "kvm_device": False,
    "host_ok": False,
    "admit_ready": False,
}


@pytest.fixture
def probes_opt_in(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_T12_PROBES", "1")
    monkeypatch.delenv("AIPLAT_EVAL_T12_GUEST_LIVE", raising=False)


def test_guest_sim_reaches_isolation_probed(probes_opt_in):
    run = run_linux_microvm_probes(mode=MODE_GUEST_SIM, admit=_LINUX_ADMIT)
    assert run["ok"] is True
    assert run["probed"] is True
    assert run["live"] is False
    assert run["sandbox_real_isolation"] is False
    assert run["process_split_authorized"] is False
    assert all(r["status"] == "guest_sim_ok" for r in run["results"])

    st = security_sec_p4_status(mode=MODE_GUEST_SIM, admit=_LINUX_ADMIT)
    assert st["slice"] == "SEC-P4"
    assert st["isolation_status"] == ISOLATION_PROBED
    assert st["isolation_probed"] is True
    assert st["isolation_covered"] is False
    assert st["accuracy_claim"] is False
    assert st["security_certification"] is False
    assert st["claim_eligible"] is False


def test_guest_sim_covered_needs_human_review(probes_opt_in):
    st = security_sec_p4_status(
        mode=MODE_GUEST_SIM,
        admit=_LINUX_ADMIT,
        human_review=True,
        human_reviewer="sec-qa",
    )
    assert st["isolation_status"] == ISOLATION_COVERED
    assert st["isolation_covered"] is True
    assert st["accuracy_claim"] is False
    assert st["sandbox_real_isolation"] is False


def test_darwin_never_probed(probes_opt_in):
    run = run_linux_microvm_probes(mode=MODE_GUEST_SIM, admit=_DARWIN_ADMIT)
    assert run["probed"] is False
    assert run["ok"] is False
    st = security_sec_p4_status(mode=MODE_GUEST_SIM, admit=_DARWIN_ADMIT)
    assert st["isolation_status"] == ISOLATION_UNKNOWN
    assert st["isolation_probed"] is False
    assert st["isolation_covered"] is False


def test_admit_not_ready_stays_unprobed(probes_opt_in):
    admit = {**_LINUX_ADMIT, "admit_ready": False, "kvm_device": False}
    run = run_linux_microvm_probes(mode=MODE_GUEST_SIM, admit=admit)
    assert run["probed"] is False
    assert all(r["status"] == "admit_not_ready" for r in run["results"])
    st = security_sec_p4_status(mode=MODE_GUEST_SIM, admit=admit)
    assert st["isolation_status"] == ISOLATION_UNKNOWN
    assert st["isolation_probed"] is False


def test_opt_in_required_for_probed(monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_T12_PROBES", raising=False)
    run = run_linux_microvm_probes(mode=MODE_GUEST_SIM, admit=_LINUX_ADMIT)
    assert run["probed"] is False
    assert run["opt_in"] is False


def _fake_hooks(*, admit_cli: bool = True, guest_boot: bool = True):
    return {
        "probe_runtime": lambda: {"ok": True, "stdout": "Firecracker v1"},
        "run_allowlisted_cli": lambda argv: {
            "ok": admit_cli,
            "exit_code": 0 if admit_cli else 126,
            "audit": {"backend": "microvm_track", "argv": list(argv)},
        },
        "guest_boot_cached": lambda: guest_boot,
        "probe_guest_boot": lambda: {
            "ok": guest_boot,
            "audit": {"guest_boot": guest_boot},
        },
        "microvm_status": lambda: {
            "guest_boot": guest_boot,
            "guest_boot_authorized": True,
            "kvm_available": True,
            "microvm_host_ok": True,
        },
        "microvm_can_admit_runners": lambda: True,
    }


def _deny_ok_executor(probe):
    return {
        "ok": True,
        "observed": "denied_by_injected_escape_executor",
        "status": "guest_live_escape_ok",
        "detail": "test_executor",
    }


def test_guest_live_incomplete_without_escape_executor(probes_opt_in, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_T12_GUEST_LIVE", "1")
    run = run_linux_microvm_probes(
        mode=MODE_GUEST_LIVE,
        admit=_LINUX_ADMIT,
        hooks=_fake_hooks(),
    )
    assert run["live"] is True
    assert run["probed"] is False
    assert run["live_evidence"]["guest_boot"] is True
    statuses = {r["status"] for r in run["results"]}
    assert "guest_escape_channel_unavailable" in statuses
    assert "guest_live_neg_control_ok" in statuses
    st = security_sec_p4_status(
        mode=MODE_GUEST_LIVE,
        admit=_LINUX_ADMIT,
        hooks=_fake_hooks(),
    )
    assert st["isolation_status"] == ISOLATION_ADMITTED
    assert st["isolation_probed"] is False
    assert st["sandbox_real_isolation"] is False


def test_guest_live_probed_with_escape_executor(probes_opt_in, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_T12_GUEST_LIVE", "1")
    run = run_linux_microvm_probes(
        mode=MODE_GUEST_LIVE,
        admit=_LINUX_ADMIT,
        hooks=_fake_hooks(),
        escape_executor=_deny_ok_executor,
    )
    assert run["live"] is True
    assert run["probed"] is True
    assert run["sandbox_real_isolation"] is False
    assert run["process_split_authorized"] is False
    st = security_sec_p4_status(
        mode=MODE_GUEST_LIVE,
        admit=_LINUX_ADMIT,
        hooks=_fake_hooks(),
        escape_executor=_deny_ok_executor,
    )
    assert st["isolation_status"] == ISOLATION_PROBED
    assert st["isolation_probed"] is True
    assert st["isolation_covered"] is False
    assert st["accuracy_claim"] is False


def test_guest_live_hooks_unavailable(probes_opt_in, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_T12_GUEST_LIVE", "1")
    monkeypatch.setattr(
        "core.apps.eval.service.security_t12_p4._load_eval_microvm_hooks",
        lambda: None,
    )
    run = run_linux_microvm_probes(mode=MODE_GUEST_LIVE, admit=_LINUX_ADMIT)
    assert run["probed"] is False
    assert all(r["status"] == "guest_live_hooks_unavailable" for r in run["results"])


def test_guest_live_requires_opt_in(probes_opt_in, monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_T12_GUEST_LIVE", raising=False)
    run = run_linux_microvm_probes(mode=MODE_GUEST_LIVE, admit=_LINUX_ADMIT)
    assert run["probed"] is False
    assert all(r["status"] == "guest_live_opt_in_required" for r in run["results"])


def test_invalid_mode_raises():
    with pytest.raises(SecurityT12P4Error):
        run_linux_microvm_probes(mode="bogus", admit=_LINUX_ADMIT)


def test_facade_wrappers(probes_opt_in):
    from core.api.core_facade import (
        eval_run_linux_microvm_probes,
        eval_security_sec_p4_status,
    )

    run = eval_run_linux_microvm_probes(mode=MODE_GUEST_SIM, admit=_LINUX_ADMIT)
    assert run["probed"] is True
    st = eval_security_sec_p4_status(mode=MODE_GUEST_SIM, admit=_LINUX_ADMIT)
    assert st["ok"] is True
    assert st["slice"] == "SEC-P4"
    assert st["accuracy_claim"] is False
