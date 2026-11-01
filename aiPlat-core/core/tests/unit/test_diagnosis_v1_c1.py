"""DIAGNOSIS_V1 C1 — store/adapters/engine/fixture metrics (no remediate)."""
from __future__ import annotations

import os
import pytest


@pytest.fixture()
def dx_db(tmp_path, monkeypatch):
    db = tmp_path / "dx.sqlite3"
    monkeypatch.setenv("AIPLAT_DIAGNOSIS_STORE_DB", str(db))
    # reset singleton
    import core.apps.diagnosis.service.store as store_mod

    store_mod._STORE = None
    yield db
    store_mod._STORE = None


def test_fixture_root_has_ten():
    from core.apps.diagnosis.service.adapters import fixture_root

    root = fixture_root()
    cases = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("dx.")]
    assert len(cases) >= 10


def test_create_collect_report_timeout_fixture(dx_db):
    from core.api.core_facade import (
        diagnosis_collect,
        diagnosis_create_case,
        diagnosis_get_report,
        diagnosis_run_report,
    )

    case = diagnosis_create_case(
        scenario="run_failure",
        subject_ref="fixture:dx.s1.tool_timeout",
        tenant_id="t-dx",
    )
    collected = diagnosis_collect(case["id"], tenant_id="t-dx")
    assert collected["evidence"]
    out = diagnosis_run_report(case["id"], tenant_id="t-dx")
    assert out["status"] in ("reported", "blocked_unknown", "blocked_stale")
    assert out["report"]["accuracy_claim"] is False
    assert all(r.get("auto_execute") is False for r in out["recommendations"])
    hyps = out["hypotheses"]
    assert hyps
    assert hyps[0]["root_cause"] == "timeout"
    assert diagnosis_get_report(case["id"], tenant_id="t-dx")


def test_unknown_and_stale_fixtures(dx_db):
    from core.api.core_facade import (
        diagnosis_collect,
        diagnosis_create_case,
        diagnosis_run_report,
    )

    u = diagnosis_create_case(
        scenario="run_failure",
        subject_ref="dx.s1.no_trace",
        tenant_id="t-dx",
    )
    diagnosis_collect(u["id"], tenant_id="t-dx")
    ou = diagnosis_run_report(u["id"], tenant_id="t-dx")
    assert ou["status"] == "blocked_unknown"
    assert ou["hypotheses"][0]["root_cause"] == "insufficient_evidence"

    s = diagnosis_create_case(
        scenario="run_failure",
        subject_ref="dx.s1.stale_kb",
        tenant_id="t-dx",
    )
    diagnosis_collect(s["id"], tenant_id="t-dx")
    os_ = diagnosis_run_report(s["id"], tenant_id="t-dx")
    assert os_["status"] == "blocked_stale"
    assert os_["hypotheses"][0]["root_cause"] == "data_stale"


def test_invalid_scenario(dx_db):
    from core.api.core_facade import diagnosis_create_case

    with pytest.raises(ValueError, match="invalid_scenario"):
        diagnosis_create_case(scenario="other", subject_ref="x", tenant_id="t-dx")


def test_fixture_metrics_rates():
    from core.apps.diagnosis.service.metrics import fixture_metrics

    m = fixture_metrics(limit=10, blind=True)
    assert m["accuracy_claim"] is False
    assert m["blind"] is True
    assert m["n"] == 10
    assert m["top1_rate"] >= 0.7
    assert m["top3_rate"] >= 0.85
    assert m["evidence_complete_rate"] >= 0.9
    assert m["bare_conclusion_count"] == 0
    assert m["unknown_correct_rate"] is None or m["unknown_correct_rate"] >= 0.9
    assert m["stale_correct_rate"] is None or m["stale_correct_rate"] >= 0.9


def test_recommendations_force_auto_execute_false(dx_db):
    from core.api.core_facade import (
        diagnosis_collect,
        diagnosis_create_case,
        diagnosis_recommendations,
        diagnosis_run_report,
    )

    case = diagnosis_create_case(
        scenario="run_failure",
        subject_ref="fixture:dx.s1.policy_tool_deny",
        tenant_id="t-dx",
    )
    diagnosis_collect(case["id"], tenant_id="t-dx")
    diagnosis_run_report(case["id"], tenant_id="t-dx")
    rec = diagnosis_recommendations(case["id"], tenant_id="t-dx")
    assert rec["auto_execute"] is False
    assert all(r.get("auto_execute") is False for r in rec["recommendations"])
