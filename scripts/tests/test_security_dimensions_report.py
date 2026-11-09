"""25-dim security coverage report — schema_ok ≠ coverage_ok."""
from __future__ import annotations

import importlib.util
import json
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


def test_repo_yaml_schema_ok(report_mod):
    r = report_mod.build_report(YAML)
    assert r["schema_ok"] is True, r.get("errors")
    assert r["dimension_count"] == 25
    assert r["security_certification"] is False
    # Honest inventory: P0 gaps remain → coverage not green
    assert "schema_ok" in r and "coverage_ok" in r
    assert r["coverage_ok"] is False


def test_missing_dimension_schema_false(report_mod, tmp_path):
    import yaml

    doc = yaml.safe_load(YAML.read_text(encoding="utf-8"))
    doc["dimensions"] = doc["dimensions"][:-1]
    p = tmp_path / "dims.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    r = report_mod.build_report(p)
    assert r["schema_ok"] is False
    assert any("dimension_count" in e for e in r["errors"])


def test_all_g_coverage_false(report_mod, tmp_path):
    import yaml

    doc = yaml.safe_load(YAML.read_text(encoding="utf-8"))
    for d in doc["dimensions"]:
        d["status"] = "G"
        d["gap"] = d.get("gap") or "forced"
        d["next"] = d.get("next") or "forced"
        d["owner"] = d.get("owner") or "test"
        d["last_reviewed"] = d.get("last_reviewed") or "2026-11-09"
        # strip V/T so we don't trip E rules; status is G
        d["evidence"] = [
            {
                "path": "docs/dummy.md",
                "level": "D",
                "verified_at": "2026-11-09",
                "owner": "test",
            }
        ]
    p = tmp_path / "all_g.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    r = report_mod.build_report(p)
    assert r["schema_ok"] is True, r.get("errors")
    assert r["coverage_ok"] is False
    assert r["gap_count"] >= 1


def test_e_with_only_d_schema_false(report_mod, tmp_path):
    import yaml

    doc = yaml.safe_load(YAML.read_text(encoding="utf-8"))
    # Force D05 to E with only D evidence
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
    p = tmp_path / "fake_e.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    r = report_mod.build_report(p)
    assert r["schema_ok"] is False
    assert any("E_requires_V_or_T" in e for e in r["errors"])


def test_e_with_vt_schema_true_slice(report_mod, tmp_path):
    import yaml

    doc = yaml.safe_load(YAML.read_text(encoding="utf-8"))
    for d in doc["dimensions"]:
        if d["id"] == "D05":
            d["status"] = "E"
            d["evidence"] = [
                {
                    "path": "aiPlat-platform/auth/mfa.py",
                    "level": "V",
                    "verified_at": "2026-11-09",
                    "owner": "test",
                }
            ]
            break
    p = tmp_path / "ok_e.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    r = report_mod.build_report(p)
    assert r["schema_ok"] is True, r.get("errors")


def test_main_strict_gaps_fails(report_mod):
    code = report_mod.main(["--path", str(YAML), "--strict-gaps"])
    assert code == 1


def test_main_schema_ok_exit_zero(report_mod):
    code = report_mod.main(["--path", str(YAML)])
    assert code == 0
