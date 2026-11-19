"""Operational 可认证路径：operational_minimum + operational_ready + 批准徽章。"""
from __future__ import annotations

from pathlib import Path

from core.harness.knowledge_pipeline import conformance_pack as cp


def test_catalog_operational_minimum_exists():
    cat = cp.load_conformance_catalog()
    assert set(cat.get("operational_minimum_ids") or []) == set(
        cp.OPERATIONAL_MINIMUM_IDS
    )
    by_id = {it["id"]: it for it in (cat.get("items") or [])}
    for oid in cp.OPERATIONAL_MINIMUM_IDS:
        assert by_id[oid]["level"] == "operational"
        assert by_id[oid]["status"] == "exists"


def test_operational_ready_without_badge():
    gate = cp.evaluate_operational_ready_gate()
    assert gate["pass"] is True, gate
    assert gate["operational_ready"] is True
    assert gate["certified"] is False
    assert gate["pilot_operational_certified"] is False


def test_pilot_operational_requires_approval():
    g0 = cp.evaluate_pilot_operational_certification()
    assert g0["pilot_operational_certified"] is False
    assert "approval_record_path_required" in g0["issues"]

    pending = (
        Path(cp._repo_root())
        / "reports/products/knowledge-system/v4.3.1/pilot-operational-approval-record.pending.json"
    )
    g1 = cp.evaluate_pilot_operational_certification(approval_record_path=str(pending))
    assert g1["operational_ready"] is True
    assert g1["pilot_operational_certified"] is False
    assert g1["certified"] is False
