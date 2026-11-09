"""SEC-P0b: T12 isolation_admitted / probed / covered state machine."""
from __future__ import annotations

import platform

from core.apps.eval.service.isolation_t12 import (
    ISOLATION_ADMITTED,
    ISOLATION_COVERED,
    ISOLATION_PROBED,
    ISOLATION_UNKNOWN,
    evaluate_isolation_status,
    load_t12_escape_probes,
    run_escape_probes,
    security_t12_p0b_status,
)


def test_probe_catalog_min_four_with_negative_control():
    cat = load_t12_escape_probes()
    assert len(cat["probes"]) >= 4
    assert any(p.get("kind") == "negative_control" for p in cat["probes"])
    assert cat["accuracy_claim"] is False


def test_admit_alone_never_covered():
    admit = {
        "os": "linux",
        "linux": True,
        "kvm_device": True,
        "host_ok": True,
        "admit_ready": True,
        "microvm_covered": False,
        "process_split_authorized": False,
    }
    st = evaluate_isolation_status(admit=admit, probe_run=None, human_review=True, human_reviewer="qa")
    assert st["isolation_status"] == ISOLATION_ADMITTED
    assert st["isolation_covered"] is False
    assert st["accuracy_claim"] is False
    assert st["process_split_authorized"] is False


def test_darwin_stays_unknown():
    admit = {
        "os": "darwin",
        "linux": False,
        "kvm_device": False,
        "host_ok": False,
        "admit_ready": False,
    }
    st = evaluate_isolation_status(admit=admit)
    assert st["isolation_status"] == ISOLATION_UNKNOWN
    assert st["isolation_covered"] is False


def test_probed_requires_completed_negative_results():
    admit = {
        "os": "linux",
        "linux": True,
        "admit_ready": True,
        "kvm_device": True,
        "host_ok": True,
    }
    probe_run = {
        "probed": False,
        "results": [
            {"probe_id": "a", "kind": "host_file", "expect": "deny", "status": "ok", "ok": True},
            {"probe_id": "b", "kind": "network", "expect": "deny", "status": "ok", "ok": True},
            {"probe_id": "c", "kind": "privilege", "expect": "deny", "status": "ok", "ok": True},
            {
                "probe_id": "d",
                "kind": "negative_control",
                "expect": "allow",
                "status": "ok",
                "ok": True,
            },
        ],
    }
    st = evaluate_isolation_status(admit=admit, probe_run=probe_run)
    assert st["isolation_status"] == ISOLATION_PROBED
    # covered needs human review
    st2 = evaluate_isolation_status(
        admit=admit, probe_run=probe_run, human_review=True, human_reviewer="sec"
    )
    assert st2["isolation_status"] == ISOLATION_COVERED
    assert st2["isolation_covered"] is True
    assert st2["accuracy_claim"] is False
    assert st2["security_certification"] is False


def test_dry_probe_run_not_probed():
    run = run_escape_probes(live=False)
    assert run["probed"] is False
    assert all(r["status"] == "not_run" for r in run["results"])


def test_p0b_status_and_facade():
    st = security_t12_p0b_status()
    assert st["slice"] == "SEC-P0b"
    assert st["accuracy_claim"] is False
    assert st["process_split_authorized"] is False
    assert st["isolation_status"] in {
        ISOLATION_UNKNOWN,
        ISOLATION_ADMITTED,
        ISOLATION_PROBED,
        ISOLATION_COVERED,
    }
    if platform.system().lower() != "linux":
        assert st["isolation_status"] == ISOLATION_UNKNOWN
    from core.api.core_facade import eval_security_sec_p0b_status

    assert eval_security_sec_p0b_status()["ok"] is True


def test_m1c_probe_exposes_isolation_status():
    from core.apps.eval.service.mode_aware_exam import probe_m1c_sandbox

    p = probe_m1c_sandbox()
    assert p["microvm_covered"] is False
    assert "isolation_status" in p
    assert p["isolation_status"] != ISOLATION_COVERED
