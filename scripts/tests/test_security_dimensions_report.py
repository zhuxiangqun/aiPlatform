"""26-dim security ledger — ledger ≠ accounted ≠ release ≠ coverage."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "scripts" / "security_dimensions_report.py"
YAML = ROOT / "reports" / "security" / "security_quality_dimensions.yaml"


def _load():
    spec = importlib.util.spec_from_file_location("security_dimensions_report_ut", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def report_mod():
    return _load()


def _dump(tmp_path, doc, name="dims.yaml"):
    import yaml

    p = tmp_path / name
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return p


def _load_doc():
    import yaml

    return yaml.safe_load(YAML.read_text(encoding="utf-8"))


def test_repo_yaml_four_states(report_mod):
    r = report_mod.build_report(YAML)
    assert r["ledger_ok"] is True, r.get("errors")
    assert r["schema_ok"] is True
    assert r["schema_ok"] == r["ledger_ok"]
    assert r["dimension_count"] == 26
    assert r["security_certification"] is False
    # D03 G owned → accounted can be true; release/coverage false
    assert r["accounted_ok"] is True
    assert r["release_ok"] is False
    assert r["coverage_ok"] is False
    assert "D03" in r["open_gap_ids"]
    assert "D03" in r["release_blocking_ids"]
    assert "D03" in r["external_dependency_ids"]
    assert "D06" not in r["open_gap_ids"]  # platform authz narrowed; gap cleared
    assert "D26" in r["open_gap_ids"]  # artifact authz pilot
    assert "D26" in r["release_blocking_ids"]
    assert "D19" in r["open_gap_ids"]


def test_missing_dimension_ledger_false(report_mod, tmp_path):
    doc = _load_doc()
    doc["dimensions"] = doc["dimensions"][:-1]
    r = report_mod.build_report(_dump(tmp_path, doc))
    assert r["ledger_ok"] is False
    assert r["schema_ok"] is False


def test_g_owned_accounted_true_release_false(report_mod, tmp_path):
    doc = _load_doc()
    # Ensure D03 looks owned G without acceptance
    for d in doc["dimensions"]:
        if d["id"] == "D03":
            d["status"] = "G"
            d["owner"] = "Security Owner"
            d["gap"] = "no external report"
            d["next"] = "RFP"
            d["release_blocking"] = True
            d.pop("release_risk_acceptance", None)
            d.pop("risk_acceptance", None)
            break
    r = report_mod.build_report(_dump(tmp_path, doc, "g_owned.yaml"))
    assert r["ledger_ok"] is True, r.get("errors")
    assert r["accounted_ok"] is True
    assert r["release_ok"] is False
    assert r["coverage_ok"] is False
    assert "D03" in r["release_blocking_ids"]


def test_g_with_valid_acceptance_release_true_slice(report_mod, tmp_path):
    doc = _load_doc()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    # Force all P0 to E empty gap except D03 G with acceptance
    for d in doc["dimensions"]:
        if not d.get("p0"):
            continue
        if d["id"] == "D03":
            d["status"] = "G"
            d["owner"] = "Security Owner"
            d["gap"] = "external"
            d["next"] = "RFP"
            d["release_blocking"] = True
            d["release_risk_acceptance"] = {
                "owner": "Security Owner",
                "reason": "ship while RFP in flight",
                "expires_at": future,
            }
            d["evidence"] = [
                {
                    "path": "docs/x.md",
                    "level": "D",
                    "verified_at": "2026-11-09",
                    "owner": "test",
                }
            ]
            continue
        d["status"] = "E"
        d["gap"] = ""
        d["release_blocking"] = False
        d["owner"] = d.get("owner") or "test"
        d["last_reviewed"] = d.get("last_reviewed") or "2026-11-09"
        d["evidence"] = [
            {
                "path": "aiPlat-platform/auth/mfa.py",
                "level": "V",
                "verified_at": "2026-11-09",
                "owner": "test",
            }
        ]
        d.pop("release_risk_acceptance", None)
    r = report_mod.build_report(_dump(tmp_path, doc, "g_acc.yaml"))
    assert r["ledger_ok"] is True, r.get("errors")
    assert r["accounted_ok"] is True
    assert r["release_ok"] is True
    assert r["coverage_ok"] is False  # D03 still G


def test_g_expired_acceptance_release_false(report_mod, tmp_path):
    doc = _load_doc()
    past = "2020-01-01T00:00:00Z"
    for d in doc["dimensions"]:
        if not d.get("p0"):
            continue
        if d["id"] == "D03":
            d["status"] = "G"
            d["owner"] = "Security Owner"
            d["gap"] = "external"
            d["next"] = "RFP"
            d["release_blocking"] = True
            d["release_risk_acceptance"] = {
                "owner": "Security Owner",
                "reason": "old",
                "expires_at": past,
            }
            continue
        d["status"] = "E"
        d["gap"] = ""
        d["release_blocking"] = False
        d["owner"] = d.get("owner") or "test"
        d["last_reviewed"] = d.get("last_reviewed") or "2026-11-09"
        d["evidence"] = [
            {
                "path": "aiPlat-platform/auth/mfa.py",
                "level": "V",
                "verified_at": "2026-11-09",
                "owner": "test",
            }
        ]
    r = report_mod.build_report(_dump(tmp_path, doc, "g_exp.yaml"))
    assert r["release_ok"] is False
    assert "D03" in r["expired_risk_ids"]


def test_i_blocking_without_acceptance_release_false(report_mod, tmp_path):
    doc = _load_doc()
    for d in doc["dimensions"]:
        if not d.get("p0"):
            continue
        d["status"] = "E"
        d["gap"] = ""
        d["release_blocking"] = False
        d["owner"] = d.get("owner") or "test"
        d["last_reviewed"] = d.get("last_reviewed") or "2026-11-09"
        d["evidence"] = [
            {
                "path": "aiPlat-platform/auth/mfa.py",
                "level": "V",
                "verified_at": "2026-11-09",
                "owner": "test",
            }
        ]
        d.pop("release_risk_acceptance", None)
    for d in doc["dimensions"]:
        if d["id"] == "D19":
            d["status"] = "I"
            d["gap"] = "sbom"
            d["next"] = "ops"
            d["release_blocking"] = True
            break
    r = report_mod.build_report(_dump(tmp_path, doc, "i_block.yaml"))
    assert r["accounted_ok"] is True
    assert r["release_ok"] is False
    assert "D19" in r["release_blocking_ids"]


def test_i_non_blocking_release_true(report_mod, tmp_path):
    doc = _load_doc()
    for d in doc["dimensions"]:
        if not d.get("p0"):
            continue
        d["status"] = "E"
        d["gap"] = ""
        d["release_blocking"] = False
        d["owner"] = d.get("owner") or "test"
        d["last_reviewed"] = d.get("last_reviewed") or "2026-11-09"
        d["evidence"] = [
            {
                "path": "aiPlat-platform/auth/mfa.py",
                "level": "V",
                "verified_at": "2026-11-09",
                "owner": "test",
            }
        ]
    for d in doc["dimensions"]:
        if d["id"] == "D19":
            d["status"] = "I"
            d["gap"] = "sbom"
            d["next"] = "ops"
            d["release_blocking"] = False
            break
    r = report_mod.build_report(_dump(tmp_path, doc, "i_ok.yaml"))
    assert r["release_ok"] is True
    assert r["coverage_ok"] is False


def test_e_with_open_gap_coverage_false(report_mod, tmp_path):
    doc = _load_doc()
    for d in doc["dimensions"]:
        if not d.get("p0"):
            continue
        d["status"] = "E"
        d["gap"] = ""
        d["release_blocking"] = False
        d["owner"] = d.get("owner") or "test"
        d["last_reviewed"] = d.get("last_reviewed") or "2026-11-09"
        d["evidence"] = [
            {
                "path": "aiPlat-platform/auth/mfa.py",
                "level": "V",
                "verified_at": "2026-11-09",
                "owner": "test",
            }
        ]
    for d in doc["dimensions"]:
        if d["id"] == "D06":
            d["gap"] = "pilot still open"
            d["release_blocking"] = True
            break
    r = report_mod.build_report(_dump(tmp_path, doc, "e_gap.yaml"))
    assert r["ledger_ok"] is True
    assert r["accounted_ok"] is True
    assert r["coverage_ok"] is False
    assert r["release_ok"] is False
    assert "D06" in r["open_gap_ids"]


def test_all_p0_e_clean_coverage_true(report_mod, tmp_path):
    doc = _load_doc()
    for d in doc["dimensions"]:
        if not d.get("p0"):
            continue
        d["status"] = "E"
        d["gap"] = ""
        d["release_blocking"] = False
        d["owner"] = d.get("owner") or "test"
        d["last_reviewed"] = d.get("last_reviewed") or "2026-11-09"
        d["evidence"] = [
            {
                "path": "aiPlat-platform/auth/mfa.py",
                "level": "V",
                "verified_at": "2026-11-09",
                "owner": "test",
            }
        ]
        d.pop("release_risk_acceptance", None)
    r = report_mod.build_report(_dump(tmp_path, doc, "all_e.yaml"))
    assert r["coverage_ok"] is True
    assert r["release_ok"] is True
    assert r["accounted_ok"] is True


def test_e_with_only_d_ledger_false(report_mod, tmp_path):
    doc = _load_doc()
    for d in doc["dimensions"]:
        if d["id"] == "D05":
            d["status"] = "E"
            d["evidence"] = [
                {
                    "path": "docs/only-doc.md",
                    "level": "D",
                    "verified_at": "2026-11-09",
                    "owner": "test",
                }
            ]
            break
    r = report_mod.build_report(_dump(tmp_path, doc, "fake_e.yaml"))
    assert r["ledger_ok"] is False
    assert any("E_requires_V_or_T" in e for e in r["errors"])


def test_main_claim_gate_fails(report_mod):
    assert report_mod.main(["--path", str(YAML), "--claim-gate"]) == 1
    assert report_mod.main(["--path", str(YAML), "--strict-gaps"]) == 1


def test_main_release_gate_fails_on_repo(report_mod):
    assert report_mod.main(["--path", str(YAML), "--release-gate"]) == 1


def test_main_ledger_ok_exit_zero(report_mod):
    assert report_mod.main(["--path", str(YAML)]) == 0


def test_accounted_true_not_enough_for_release_gate(report_mod, tmp_path):
    """accounted true + coverage false must not make release-gate exit 0 on repo-like gaps."""
    doc = _load_doc()
    r = report_mod.build_report(_dump(tmp_path, doc, "repo_like.yaml"))
    assert r["accounted_ok"] is True
    assert r["release_ok"] is False
    code = report_mod.main(["--path", str(_dump(tmp_path, doc, "repo_gate.yaml")), "--release-gate"])
    assert code == 1
