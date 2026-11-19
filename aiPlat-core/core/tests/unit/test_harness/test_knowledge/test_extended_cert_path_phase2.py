"""Extended 可认证路径：extended_minimum + extended_ready + 批准徽章。"""
from __future__ import annotations

from pathlib import Path

from core.harness.knowledge_pipeline import conformance_pack as cp


def test_catalog_extended_minimum_exists():
    cat = cp.load_conformance_catalog()
    assert set(cat.get("extended_minimum_ids") or []) == set(cp.EXTENDED_MINIMUM_IDS)
    by_id = {it["id"]: it for it in (cat.get("items") or [])}
    for eid in cp.EXTENDED_MINIMUM_IDS:
        assert by_id[eid]["level"] == "extended"
        assert by_id[eid]["status"] == "exists"


def test_extended_ready_without_badge():
    gate = cp.evaluate_extended_ready_gate()
    assert gate["pass"] is True, gate
    assert gate["extended_ready"] is True
    assert gate["certified"] is False
    assert gate["pilot_extended_certified"] is False
    assert gate["extended_claim"] is False


def test_pilot_extended_requires_approval():
    g0 = cp.evaluate_pilot_extended_certification()
    assert g0["pilot_extended_certified"] is False
    assert "approval_record_path_required" in g0["issues"]

    pending = (
        Path(cp._repo_root())
        / "reports/products/knowledge-system/v4.3.1/pilot-extended-approval-record.pending.json"
    )
    g1 = cp.evaluate_pilot_extended_certification(approval_record_path=str(pending))
    assert g1["extended_ready"] is True
    assert g1["pilot_extended_certified"] is False
    assert g1["certified"] is False
