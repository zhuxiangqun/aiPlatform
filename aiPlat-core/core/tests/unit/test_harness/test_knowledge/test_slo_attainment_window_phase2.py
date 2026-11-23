"""SLO 生产达标窗口（显式 residual）；须窗口达标 + 非作者批准；certified 恒假。"""
from __future__ import annotations

import json
from pathlib import Path

from core.api import core_facade
from core.harness.knowledge_pipeline.slo_telemetry import (
    evaluate_slo_attainment_window,
    record_slo_sample,
)

_REPO = Path(__file__).resolve().parents[6]
_APPROVED = (
    _REPO
    / "reports/products/knowledge-system/v4.3.1/pilot-slo-attainment-approval-record.approved.json"
)
_PENDING = (
    _REPO
    / "reports/products/knowledge-system/v4.3.1/pilot-slo-attainment-approval-record.pending.json"
)


def _seed_ok(db: str, tenant: str = "t-att") -> None:
    for mid, val in (
        ("action_success_rate", 1.0),
        ("query_p95_ms", 50.0),
        ("citation_coverage", 1.0),
    ):
        record_slo_sample(mid, val, tenant_id=tenant, ok=True, db_path=db)


def test_attainment_requires_approval_path(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    _seed_ok(db)
    gate = evaluate_slo_attainment_window(
        "t-att", db_path=db, include_live=False, approval_record_path=None
    )
    assert gate["wiring_ok"] is True
    assert gate["window_meets_targets"] is True
    assert gate["approval_ok"] is False
    assert gate["attainment_ok"] is False
    assert gate["certified"] is False
    assert "approval_record_path_required" in gate["issues"]


def test_attainment_pending_approval_blocks(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    _seed_ok(db)
    gate = evaluate_slo_attainment_window(
        "t-att",
        db_path=db,
        include_live=False,
        approval_record_path=str(_PENDING),
    )
    assert gate["window_meets_targets"] is True
    assert gate["approval_ok"] is False
    assert gate["attainment_ok"] is False
    assert "approval_not_approved" in gate["issues"]


def test_attainment_ok_with_approved_and_window(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    _seed_ok(db)
    gate = evaluate_slo_attainment_window(
        "t-att",
        db_path=db,
        include_live=False,
        approval_record_path=str(_APPROVED),
    )
    assert gate["wiring_ok"] is True
    assert gate["window_meets_targets"] is True
    assert gate["approval_ok"] is True
    assert gate["attainment_ok"] is True
    # 为什么：达标窗口不得冒充 Full / N24 certified
    assert gate["certified"] is False
    assert gate["n24_full_conformance"] is False


def test_misses_target_blocks_even_with_approval(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    record_slo_sample(
        "action_success_rate", 0.5, tenant_id="t-miss", ok=False, db_path=db
    )
    record_slo_sample(
        "query_p95_ms", 50.0, tenant_id="t-miss", ok=True, db_path=db
    )
    record_slo_sample(
        "citation_coverage", 1.0, tenant_id="t-miss", ok=True, db_path=db
    )
    gate = evaluate_slo_attainment_window(
        "t-miss",
        db_path=db,
        include_live=False,
        approval_record_path=str(_APPROVED),
    )
    assert gate["approval_ok"] is True
    assert gate["window_meets_targets"] is False
    assert gate["attainment_ok"] is False
    assert any(i.startswith("misses_target:") for i in gate["issues"])


def test_wrong_scope_approval_rejected(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    _seed_ok(db, "t-scope")
    bad = tmp_path / "full-approval.json"
    bad.write_text(
        json.dumps(
            {
                "status": "approved",
                "decision": "conditional",
                "scope": "pilot lock-service full N24 certification",
                "approvers": [{"name": "x", "is_author": False}],
                "effective_date": "2026-11-19",
            }
        ),
        encoding="utf-8",
    )
    gate = evaluate_slo_attainment_window(
        "t-scope",
        db_path=db,
        include_live=False,
        approval_record_path=str(bad),
    )
    assert gate["approval_ok"] is False
    assert gate["attainment_ok"] is False
    assert "approval_scope_not_slo_attainment" in gate["issues"]


def test_facade_attainment_delegates(tmp_path: Path):
    db = str(tmp_path / "slo.db")
    _seed_ok(db, "t-facade-att")
    gate = core_facade.evaluate_knowledge_slo_attainment_window(
        "t-facade-att",
        db_path=db,
        include_live=False,
        approval_record_path=str(_APPROVED),
    )
    assert gate["attainment_ok"] is True
    assert gate["certified"] is False
