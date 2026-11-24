"""N13 deepen + residual：Operational 校准流水线 / 样本 ECE；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.api.core_facade import (
    compute_ece_from_samples as facade_ece,
    evaluate_calibration_pipeline_gate,
    run_calibration_pipeline_suite,
)
from core.harness.knowledge_pipeline.confidence_calibration import (
    apply_calibration_ceiling,
    compute_ece_from_samples,
    evaluate_calibration_pipeline_gate as core_gate,
    publish_calibration_report,
    run_calibration_pipeline_suite as core_suite,
)
from core.harness.knowledge_pipeline.fact_ledger import FactLedger

ROOT = Path(__file__).resolve().parents[6]


@pytest.mark.asyncio
async def test_suite_and_gate_honesty():
    suite = await core_suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["certified"] is False
    assert suite["n13_full_conformance"] is False
    assert suite.get("n13_calibration_freeze") is True
    assert suite.get("accuracy_claim") is False
    ids = {c["id"] for c in suite["cases"]}
    assert "ece_train_opt_in" in ids
    assert "ece_train_unavailable" in ids
    gate = core_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    bad = dict(suite)
    bad["certified"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


@pytest.mark.asyncio
async def test_facade_suite():
    suite = await run_calibration_pipeline_suite()
    assert suite["ok"] is True
    gate = evaluate_calibration_pipeline_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_ece_train_unavailable_default():
    r = compute_ece_from_samples([{"confidence": 0.9, "correct": True}])
    assert r["status"] == "ece_training_unavailable"
    assert r["accuracy_claim"] is False
    fr = facade_ece([{"confidence": 0.5, "correct": False}])
    assert fr["status"] == "ece_training_unavailable"


@pytest.mark.asyncio
async def test_gateway_applies_ceiling(tmp_path):
    from datetime import datetime, timedelta, timezone

    db = str(tmp_path / "cal.db")
    lg = FactLedger(
        db_path=str(tmp_path / "fl.sqlite3"),
        raw_dir=tmp_path / "raw",
    )
    await lg.initialize()
    src = await lg.register_source(
        tenant_id="t1",
        collection_id="c1",
        kind="file",
        uri="file://n13/x.txt",
        content=b"x",
        connector="n13",
        domain_id="d1",
    )
    await lg.put_fact(
        tenant_id="t1",
        collection_id="c1",
        subject="A:1",
        predicate="p",
        object="v",
        evidence=[
            {
                "source_id": src["source_id"],
                "locator": "1",
                "quote": "v",
                "fetched_at": src["fetched_at"],
            }
        ],
        source_policy="p",
        extractor_version="t",
        review_status="published",
        confidence=0.9,
        allow_bootstrap_published=True,
        domain_id="d1",
    )
    # 无校准 → high 被封顶 medium
    gw = await lg.query_facts_gateway(
        tenant_id="t1",
        query="v",
        domain_id="d1",
        calibration_db_path=db,
    )
    assert gw["confidence"] == "medium"
    assert gw["calibration_capped"] is True

    future = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
    publish_calibration_report(
        tenant_id="t1",
        domain="d1",
        query_type="fact_gateway",
        dataset_version="g1",
        sample_size=120,
        label_protocol="dual",
        inter_annotator_agreement=0.3,
        weights={"w": 1},
        calibration_version="c1",
        ece=0.02,
        brier=0.1,
        high_precision=0.95,
        coverage=0.8,
        approved_by="o",
        valid_until=future,
        db_path=db,
    )
    gw2 = await lg.query_facts_gateway(
        tenant_id="t1",
        query="v",
        domain_id="d1",
        calibration_db_path=db,
    )
    assert gw2["confidence"] == "high"
    assert gw2["calibration_capped"] is False


def test_apply_ceiling_without_domain():
    out = apply_calibration_ceiling(
        tenant_id="t1",
        domain="",
        query_type="fact_gateway",
        confidence="high",
    )
    assert out["confidence"] == "high"
    assert out["capped"] is False


def test_docs_and_wiring_state():
    cal = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "confidence_calibration.py"
    )
    text = cal.read_text(encoding="utf-8")
    assert "apply_calibration_ceiling" in text
    assert "compute_ece_from_samples" in text
    assert "run_calibration_pipeline_suite" in text
    fl = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "fact_ledger.py"
    )
    assert "calibration_db_path" in fl.read_text(encoding="utf-8")
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    ftext = facade.read_text(encoding="utf-8")
    assert "run_calibration_pipeline_suite" in ftext
    assert "compute_ece_from_samples" in ftext
