"""W10 Confidence Calibration：门槛校验；失败最高 medium。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.harness.knowledge_pipeline import confidence_calibration as cc


def _future(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")


def _past(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def test_publish_pass_allows_high(tmp_path):
    db = str(tmp_path / "cal.db")
    out = cc.publish_calibration_report(
        tenant_id="t1",
        domain="lock-service",
        query_type="object_lookup",
        dataset_version="gold-v1",
        sample_size=120,
        label_protocol="dual-label-20pct",
        inter_annotator_agreement=0.25,
        weights={"evidence": 0.6, "model": 0.4},
        calibration_version="cal-v1",
        ece=0.03,
        brier=0.12,
        high_precision=0.92,
        coverage=0.8,
        approved_by="domain-owner",
        valid_until=_future(),
        model_version="m1",
        index_version="idx1",
        db_path=db,
    )
    assert out["status"] == "approved"
    assert out["active"] is True
    assert out["gate"]["pass"] is True

    resolved = cc.resolve_max_confidence(
        tenant_id="t1",
        domain="lock-service",
        query_type="object_lookup",
        requested="high",
        db_path=db,
    )
    assert resolved["allowed"] == "high"
    assert resolved["capped"] is False


def test_ece_fail_caps_to_medium(tmp_path):
    db = str(tmp_path / "cal.db")
    out = cc.publish_calibration_report(
        tenant_id="t1",
        domain="lock-service",
        query_type="faq",
        dataset_version="gold-v1",
        sample_size=120,
        label_protocol="dual",
        inter_annotator_agreement=0.3,
        weights={"w": 1},
        calibration_version="cal-v1",
        ece=0.12,
        brier=0.2,
        high_precision=0.95,
        coverage=0.7,
        approved_by="owner",
        valid_until=_future(),
        db_path=db,
    )
    assert out["status"] == "failed"
    assert out["active"] is False
    assert "ece_above_threshold" in out["gate"]["issues"]

    resolved = cc.resolve_max_confidence(
        tenant_id="t1",
        domain="lock-service",
        query_type="faq",
        requested="high",
        db_path=db,
    )
    assert resolved["allowed"] == "medium"
    assert resolved["capped"] is True


def test_missing_or_expired_caps_to_medium(tmp_path):
    db = str(tmp_path / "cal.db")
    missing = cc.resolve_max_confidence(
        tenant_id="t1",
        domain="lock-service",
        query_type="missing",
        requested="high",
        db_path=db,
    )
    assert missing["allowed"] == "medium"
    assert missing["calibration"]["valid"] is False

    expired = cc.publish_calibration_report(
        tenant_id="t1",
        domain="lock-service",
        query_type="stale",
        dataset_version="gold-v1",
        sample_size=120,
        label_protocol="dual",
        inter_annotator_agreement=0.3,
        weights={"w": 1},
        calibration_version="cal-v1",
        ece=0.02,
        brier=0.1,
        high_precision=0.95,
        coverage=0.7,
        approved_by="owner",
        valid_until=_past(),
        db_path=db,
    )
    assert expired["status"] == "failed"
    assert "expired" in expired["gate"]["issues"]


def test_cross_tenant_hidden(tmp_path):
    db = str(tmp_path / "cal.db")
    out = cc.publish_calibration_report(
        tenant_id="t1",
        domain="lock-service",
        query_type="object_lookup",
        dataset_version="gold-v1",
        sample_size=120,
        label_protocol="dual",
        inter_annotator_agreement=0.3,
        weights={"w": 1},
        calibration_version="cal-v1",
        ece=0.02,
        brier=0.1,
        high_precision=0.95,
        coverage=0.7,
        approved_by="owner",
        valid_until=_future(),
        db_path=db,
    )
    cid = out["calibration_id"]
    assert cc.get_calibration_report(cid, tenant_id="t2", db_path=db) is None
    assert (
        cc.validate_calibration_report(cid, tenant_id="t2", db_path=db)["status"]
        == "not_found"
    )
