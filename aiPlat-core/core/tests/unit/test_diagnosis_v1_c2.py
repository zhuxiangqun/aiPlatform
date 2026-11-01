"""DIAGNOSIS_V1 C2 — reason_codes, counter_evidence, eval/ontology adapters."""
from __future__ import annotations

import pytest


@pytest.fixture()
def dx_db(tmp_path, monkeypatch):
    db = tmp_path / "dx-c2.sqlite3"
    monkeypatch.setenv("AIPLAT_DIAGNOSIS_STORE_DB", str(db))
    import core.apps.diagnosis.service.store as store_mod

    store_mod._STORE = None
    yield db
    store_mod._STORE = None


def test_report_v1_reason_codes_on_unknown(dx_db):
    from core.api.core_facade import (
        diagnosis_collect,
        diagnosis_create_case,
        diagnosis_run_report,
    )

    u = diagnosis_create_case(
        scenario="run_failure",
        subject_ref="dx.s1.no_trace",
        tenant_id="t-dx-c2",
    )
    diagnosis_collect(u["id"], tenant_id="t-dx-c2")
    out = diagnosis_run_report(u["id"], tenant_id="t-dx-c2")
    assert out["status"] == "blocked_unknown"
    assert out["report"]["schema_version"] == "diagnosis.report.v1"
    unc = out["report"]["uncertainty"]
    assert "reason_codes" in unc
    assert "no_trace" in unc["reason_codes"] or "insufficient_evidence" in unc["reason_codes"]
    assert out["report"]["accuracy_claim"] is False


def test_counter_evidence_when_competing_hyps():
    from core.apps.diagnosis.service.engine import diagnose_case

    evidence = [
        {"id": "e-sys", "source": "aiplat", "kind": "syscall", "ref": "r1", "freshness": "fresh"},
        {"id": "e-tool", "source": "pi", "kind": "tool_result", "ref": "t1", "freshness": "fresh"},
    ]
    payload = {
        "syscall": {"error": "timeout waiting for tool result", "duration_ms": 35000, "timeout_seconds": 30},
        "tool_result": {"ok": False, "status": 422},
    }
    out = diagnose_case(case_id="c-comp", evidence=evidence, payload=payload, expected=None)
    hyps = out["hypotheses"]
    assert len(hyps) >= 2
    assert any(h.get("counter_evidence_ids") for h in hyps)
    assert out["report"]["schema_version"] == "diagnosis.report.v1"
    assert isinstance(out["report"].get("top_confidence"), float)


def test_live_adapters_include_eval_and_ontology():
    from core.apps.diagnosis.service.adapters import collect_live_stubs

    bundle = collect_live_stubs(scenario="run_failure", subject_ref="subj-x")
    sources = {e.get("source") for e in bundle["evidence"]}
    assert "evaluation" in sources
    assert "ontology" in sources
    assert bundle["adapters"].get("ontology") == "read_only"
    assert bundle["adapters"].get("evaluation") == "read_only"


def test_s2_prompt_edit_keeps_confidence(dx_db):
    from core.api.core_facade import (
        diagnosis_collect,
        diagnosis_create_case,
        diagnosis_run_report,
    )

    case = diagnosis_create_case(
        scenario="version_regression",
        subject_ref="fixture:dx.s2.prompt_edit",
        tenant_id="t-dx-c2",
    )
    diagnosis_collect(case["id"], tenant_id="t-dx-c2")
    out = diagnosis_run_report(case["id"], tenant_id="t-dx-c2")
    assert out["hypotheses"][0]["root_cause"] == "prompt_regression"
    assert out["report"]["top_confidence"] >= 0.5
    assert "counter_evidence_ids" in out["hypotheses"][0]
