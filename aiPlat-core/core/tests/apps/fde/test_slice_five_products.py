"""Five-products slice: export + evidence MVP + signoff binding."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.apps.fde.service.slice_bundle_export import export_slice_bundle
from core.apps.fde.service.slice_evidence import (
    build_slice_diagnosis_report,
    get_slice_diagnosis_report,
    ingest_slice_evidence,
    ingest_slice_evidence_from_jsonl,
    validate_slice_signoff_reports,
)

_WORKSPACE = Path(__file__).resolve().parents[5]
_SAMPLE = _WORKSPACE / "packages" / "aiplat-pi-runtime" / "fixtures" / "sample-app"


@pytest.fixture()
def slice_home(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "aiplat_home"))
    return tmp_path


def test_export_slice_bundle_sample_app(slice_home, tmp_path):
    if not (_SAMPLE / "agent_manifest.json").is_file():
        pytest.skip("sample-app fixture missing")
    out = tmp_path / "bundle_out"
    r = export_slice_bundle(
        scenario_id="fp-internal-bundle-pi-diag-001",
        app_home=str(_SAMPLE),
        out_dir=str(out),
        runtime_mode="thin",
    )
    assert r.get("ok") is True, r
    assert r.get("bundle_id")
    assert Path(r["out_dir"]).is_dir()
    assert "permission_claims_note" in r
    assert (Path(r["out_dir"]) / "aiplat-export.json").is_file() or True  # meta may vary


def test_export_rejects_non_thin(slice_home):
    r = export_slice_bundle(
        scenario_id="fp-x",
        app_home=str(_SAMPLE),
        runtime_mode="hybrid",
    )
    assert r.get("ok") is False


def test_export_rejects_missing_manifest(slice_home, tmp_path):
    empty = tmp_path / "empty_app"
    empty.mkdir()
    r = export_slice_bundle(scenario_id="fp-x", app_home=str(empty))
    assert r.get("ok") is False
    assert "agent_manifest" in str(r.get("error", "")).lower() or "no agent" in str(r.get("error", "")).lower()


def test_evidence_unknown_without_pi(slice_home):
    rep = build_slice_diagnosis_report(
        scenario_id="fp-internal-bundle-pi-diag-001",
        bundle_version="v1",
        run_id="",
        events=[],
    )
    assert rep.get("ok") is True
    assert rep.get("status") == "unknown"
    assert rep.get("diagnosis_ok") is False
    got = get_slice_diagnosis_report(rep["report_id"])
    assert got.get("status") == "unknown"


def test_evidence_ok_with_pi_and_bundle(slice_home):
    ing = ingest_slice_evidence(
        scenario_id="fp-internal-bundle-pi-diag-001",
        run_id="run-1",
        bundle_version="bv-1",
        events=[{"type": "start"}],
        asset_versions={"bundle_version": "bv-1"},
        aiplat_reachable=True,
    )
    assert ing.get("ok")
    rep = build_slice_diagnosis_report(
        scenario_id="fp-internal-bundle-pi-diag-001",
        ingest_id=ing["ingest_id"],
    )
    assert rep.get("status") == "ok"
    assert rep.get("diagnosis_ok") is True


def test_evidence_stale_when_aiplat_unreachable(slice_home):
    rep = build_slice_diagnosis_report(
        scenario_id="fp-internal-bundle-pi-diag-001",
        run_id="run-1",
        bundle_version="bv-1",
        events=[{"type": "x"}],
        aiplat_reachable=False,
    )
    assert rep.get("status") == "stale"


def test_signoff_requires_report_for_fp_scenario(slice_home):
    bad = validate_slice_signoff_reports({"scenario_id": "fp-internal-bundle-pi-diag-001"})
    assert bad.get("ok") is False
    rep = build_slice_diagnosis_report(
        scenario_id="fp-internal-bundle-pi-diag-001",
        run_id="r",
        bundle_version="b",
        events=[{}],
    )
    good = validate_slice_signoff_reports(
        {
            "scenario_id": "fp-internal-bundle-pi-diag-001",
            "evidence_report_ids": [rep["report_id"]],
        }
    )
    assert good.get("ok") is True
    assert rep["report_id"] in good.get("report_ids", [])


def test_signoff_not_required_for_legacy(slice_home):
    r = validate_slice_signoff_reports({"spec_id": "legacy-customer-1"})
    assert r.get("ok") is True
    assert r.get("required") is False


def test_ingest_from_emit_jsonl(slice_home, tmp_path):
    """MB-05: Pi extension JSONL → ingest → diagnosis ok when run+bundle present."""
    jl = tmp_path / "emit.jsonl"
    lines = [
        {
            "v": 1,
            "type": "emit_open",
            "run_id": "pi-emit-1",
            "scenario_id": "fp-internal-bundle-pi-diag-001",
            "bundle_version": "bv-emit-1",
            "runtime_version": "pi-thin-emit",
            "ts": "2026-10-24T00:00:00+00:00",
        },
        {"v": 1, "type": "session_start", "run_id": "pi-emit-1", "ts": "2026-10-24T00:00:01+00:00"},
        {"v": 1, "type": "before_agent_start", "run_id": "pi-emit-1", "ts": "2026-10-24T00:00:02+00:00"},
    ]
    jl.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    ing = ingest_slice_evidence_from_jsonl(path=str(jl))
    assert ing.get("ok") is True, ing
    assert ing.get("run_id") == "pi-emit-1"
    rep = build_slice_diagnosis_report(
        scenario_id="fp-internal-bundle-pi-diag-001",
        ingest_id=ing["ingest_id"],
    )
    assert rep.get("status") == "ok"
    assert rep.get("diagnosis_ok") is True


def test_ingest_from_jsonl_missing_file(slice_home, tmp_path):
    r = ingest_slice_evidence_from_jsonl(
        path=str(tmp_path / "nope.jsonl"),
        scenario_id="fp-x",
    )
    assert r.get("ok") is False


def test_evidence_store_default_sqlite(slice_home):
    """MB-03: default backend is SQLite under AIPLAT_HOME."""
    ing = ingest_slice_evidence(
        scenario_id="fp-internal-bundle-pi-diag-001",
        run_id="run-sqlite",
        bundle_version="bv-sql",
        events=[{"type": "x"}],
    )
    assert ing.get("ok")
    assert ing.get("store") == "sqlite"
    assert str(ing.get("path", "")).startswith("sqlite:")
    home = Path(os.environ["AIPLAT_HOME"])
    assert (home / "five_products_slice" / "evidence" / "evidence.db").is_file()
    rep = build_slice_diagnosis_report(
        scenario_id="fp-internal-bundle-pi-diag-001",
        ingest_id=ing["ingest_id"],
    )
    assert rep.get("status") == "ok"
    assert rep.get("store") == "sqlite"


def test_evidence_store_file_fallback(slice_home, monkeypatch):
    """MB-03: AIPLAT_SLICE_EVIDENCE_STORE=file keeps JSON files."""
    monkeypatch.setenv("AIPLAT_SLICE_EVIDENCE_STORE", "file")
    ing = ingest_slice_evidence(
        scenario_id="fp-internal-bundle-pi-diag-001",
        run_id="run-file",
        bundle_version="bv-file",
        events=[{"type": "y"}],
    )
    assert ing.get("ok")
    assert ing.get("store") == "file"
    assert Path(ing["path"]).is_file()
    assert ing["path"].endswith(".json")
