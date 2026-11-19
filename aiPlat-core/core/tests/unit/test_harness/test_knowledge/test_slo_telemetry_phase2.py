"""F1 deepen：知识系统 SLO 遥测接线；wiring≠attainment；空样本不绿。"""
from __future__ import annotations

from pathlib import Path

from core.api import core_facade
from core.harness.knowledge_pipeline.slo_telemetry import (
    evaluate_slo_wiring_gate,
    get_slo_snapshot,
    record_slo_sample,
)


def test_record_sample_tenant_scoped(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    a = record_slo_sample(
        "action_success_rate",
        1.0,
        tenant_id="t-a",
        domain_id="lock-service",
        source="test",
        ok=True,
        db_path=db,
    )
    b = record_slo_sample(
        "action_success_rate",
        0.0,
        tenant_id="t-b",
        domain_id="lock-service",
        source="test",
        ok=False,
        db_path=db,
    )
    assert a["status"] == "ok"
    assert b["status"] == "ok"
    snap_a = get_slo_snapshot("t-a", db_path=db, include_live=False)
    snap_b = get_slo_snapshot("t-b", db_path=db, include_live=False)
    assert snap_a["metrics"]["action_success_rate"]["samples"] == 1
    assert snap_b["metrics"]["action_success_rate"]["samples"] == 1
    assert snap_a["metrics"]["action_success_rate"]["computed"] == 1.0
    assert snap_b["metrics"]["action_success_rate"]["computed"] == 0.0


def test_snapshot_exposes_targets_and_samples(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    for mid, val in (
        ("action_success_rate", 1.0),
        ("query_p95_ms", 120.0),
        ("citation_coverage", 1.0),
    ):
        record_slo_sample(mid, val, tenant_id="t1", ok=True, db_path=db)
    snap = get_slo_snapshot("t1", db_path=db, include_live=False)
    assert snap["status"] == "ok"
    assert "action_success_rate" in snap["targets"]
    assert snap["targets"]["query_p95_ms"]["target"] == 2000.0
    assert snap["metrics"]["query_p95_ms"]["computed"] == 120.0
    assert snap["metrics"]["citation_coverage"]["samples"] == 1
    assert "not production attainment" in (snap.get("note") or "")


def test_wiring_gate_honesty_empty_not_green(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    gate = evaluate_slo_wiring_gate("t-empty", db_path=db, include_live=False)
    assert gate["status"] == "ok"
    assert gate["wiring_ok"] is False
    assert gate["attainment_ok"] is False
    assert gate["certified"] is False
    assert gate["n24_full_conformance"] is False
    assert any(i.startswith("no_samples:") for i in gate["issues"])


def test_wiring_gate_pass_attainment_still_false(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    for mid, val in (
        ("action_success_rate", 1.0),
        ("query_p95_ms", 50.0),
        ("citation_coverage", 1.0),
    ):
        record_slo_sample(mid, val, tenant_id="t-ok", ok=True, db_path=db)
    gate = evaluate_slo_wiring_gate("t-ok", db_path=db, include_live=False)
    assert gate["wiring_ok"] is True
    assert gate["issues"] == []
    assert gate["attainment_ok"] is False
    assert gate["certified"] is False


def test_facade_delegates_to_slo_telemetry(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    out = core_facade.record_knowledge_slo_sample(
        "query_p95_ms",
        80.0,
        tenant_id="t-facade",
        source="test",
        db_path=db,
    )
    assert out["status"] == "ok"
    snap = core_facade.get_knowledge_slo_snapshot(
        "t-facade", db_path=db, include_live=False
    )
    assert snap["metrics"]["query_p95_ms"]["samples"] == 1
    gate = core_facade.evaluate_knowledge_slo_wiring_gate(
        "t-facade", db_path=db, include_live=False
    )
    assert gate["wiring_ok"] is False  # only one metric sampled
    assert gate["attainment_ok"] is False
    assert gate["certified"] is False


def test_record_rejects_empty_tenant(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    out = record_slo_sample(
        "action_success_rate", 1.0, tenant_id="", db_path=db
    )
    assert out["status"] == "error"
    assert out["reason"] == "tenant_id_required"
