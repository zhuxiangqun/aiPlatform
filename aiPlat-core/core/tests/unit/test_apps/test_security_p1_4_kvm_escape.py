"""P1-4: KVM escape harness (importlib; avoid Py3.9 eval package import)."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
ISO_PATH = ROOT / "core" / "apps" / "eval" / "service" / "isolation_t12.py"
P4_PATH = ROOT / "core" / "apps" / "eval" / "service" / "security_t12_p4.py"
P14_PATH = ROOT / "core" / "apps" / "eval" / "service" / "security_p1_4_kvm_escape.py"

_LINUX_ADMIT = {
    "os": "linux",
    "linux": True,
    "kvm_device": True,
    "host_ok": True,
    "admit_ready": True,
    "microvm_covered": False,
    "process_split_authorized": False,
}


def _ensure_pkg(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def p14():
    for pkg in ("core", "core.apps", "core.apps.eval", "core.apps.eval.service"):
        _ensure_pkg(pkg)
    iso = _load("core.apps.eval.service.isolation_t12", ISO_PATH)
    sys.modules["core.apps.eval.service.isolation_t12"] = iso
    # stub mode_aware_exam for admit probe inside p4
    mae = types.ModuleType("core.apps.eval.service.mode_aware_exam")

    def _probe():
        return dict(_LINUX_ADMIT)

    mae.probe_linux_microvm_host = _probe  # type: ignore[attr-defined]
    sys.modules["core.apps.eval.service.mode_aware_exam"] = mae
    p4 = _load("core.apps.eval.service.security_t12_p4", P4_PATH)
    sys.modules["core.apps.eval.service.security_t12_p4"] = p4
    return _load("core.apps.eval.service.security_p1_4_kvm_escape", P14_PATH)


@pytest.fixture
def probes_env(monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_T12_PROBES", "1")
    monkeypatch.delenv("AIPLAT_EVAL_P1_4_LIVE", raising=False)
    monkeypatch.delenv("AIPLAT_EVAL_T12_GUEST_LIVE", raising=False)


def test_catalog_has_required_kinds(p14):
    cat = p14.load_p14_escape_probes()
    kinds = {p["kind"] for p in cat["probes"]}
    assert kinds >= p14.REQUIRED_KINDS
    assert cat["security_certification"] is False


def test_http_rejected_as_escape(p14):
    with pytest.raises(p14.SecurityP14Error, match="http_is_not_escape"):
        p14.assert_not_http_escape(evidence_kind="http_only")
    with pytest.raises(p14.SecurityP14Error, match="http_is_not_escape"):
        p14.run_p1_4_kvm_escape(evidence_kind="attack_sim", admit=_LINUX_ADMIT)


def test_guest_sim_reaches_probed_not_covered(p14, probes_env):
    out = p14.run_p1_4_kvm_escape(
        mode="guest_sim",
        admit=_LINUX_ADMIT,
        evidence_kind="kvm_guest",
    )
    assert out["ok"] is True
    assert out["probed"] is True
    assert out["isolation_probed"] is True
    assert out["isolation_covered"] is False
    assert out["isolation_status"] == "isolation_probed"
    assert out["accuracy_claim"] is False
    assert out["security_certification"] is False
    assert set(out["required_kinds"]) >= p14.REQUIRED_KINDS


def test_guest_sim_human_review_can_cover(p14, probes_env):
    out = p14.run_p1_4_kvm_escape(
        mode="guest_sim",
        admit=_LINUX_ADMIT,
        human_review=True,
        human_reviewer="sec-qa",
    )
    assert out["isolation_covered"] is True
    assert out["accuracy_claim"] is False


def test_live_requires_guest_boot_and_channel(p14, probes_env, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_P1_4_LIVE", "1")
    monkeypatch.setenv("AIPLAT_EVAL_T12_GUEST_LIVE", "1")
    no_boot = p14.run_p1_4_kvm_escape(
        mode="guest_live",
        admit=_LINUX_ADMIT,
        guest_boot=False,
        guest_channel=p14.scripted_guest_channel(),
    )
    assert no_boot["error"] == "guest_boot_required"
    assert no_boot["isolation_probed"] is False

    no_ch = p14.run_p1_4_kvm_escape(
        mode="guest_live",
        admit=_LINUX_ADMIT,
        guest_boot=True,
        guest_channel=None,
    )
    assert no_ch["error"] == "guest_channel_required"


def test_live_scripted_channel_probed(p14, probes_env, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_P1_4_LIVE", "1")
    monkeypatch.setenv("AIPLAT_EVAL_T12_GUEST_LIVE", "1")
    out = p14.run_p1_4_kvm_escape(
        mode="guest_live",
        admit=_LINUX_ADMIT,
        guest_boot=True,
        guest_channel=p14.scripted_guest_channel(deny_escape=False),
        evidence_kind="kvm_guest",
    )
    assert out["ok"] is True
    assert out["probed"] is True
    assert out["isolation_probed"] is True
    assert out["isolation_covered"] is False
    assert out["live_evidence"]["guest_boot"] is True
    assert out["live_evidence"]["http_is_escape"] is False


def test_live_escape_detected_not_probed(p14, probes_env, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_P1_4_LIVE", "1")
    monkeypatch.setenv("AIPLAT_EVAL_T12_GUEST_LIVE", "1")
    out = p14.run_p1_4_kvm_escape(
        mode="guest_live",
        admit=_LINUX_ADMIT,
        guest_boot=True,
        guest_channel=p14.scripted_guest_channel(deny_escape=True),
    )
    assert out["probed"] is False
    assert out["isolation_probed"] is False


def test_status_inventory(p14):
    st = p14.security_p1_4_status()
    assert st["schema"] == "eval.security_p1_4_status.v1"
    assert st["required_kinds_met"] is True
    assert st["max_auto_status"] == "isolation_probed"
    assert st["security_certification"] is False
