"""全量可认证路径：full_ready + 三级徽章 + 独立全量批准。"""
from __future__ import annotations

from pathlib import Path

from core.harness.knowledge_pipeline import conformance_pack as cp


def test_full_ready_without_certified():
    gate = cp.evaluate_full_ready_gate()
    assert gate["pass"] is True, gate
    assert gate["full_ready"] is True
    assert gate["certified"] is False
    assert gate["n24_full_conformance"] is False


def test_full_cert_requires_independent_approval():
    g0 = cp.evaluate_full_certification()
    assert g0["certified"] is False
    assert g0["n24_full_conformance"] is False
    assert "approval_record_path_required" in g0["issues"]

    pending = (
        Path(cp._repo_root())
        / "reports/products/knowledge-system/v4.3.1/pilot-full-approval-record.pending.json"
    )
    g1 = cp.evaluate_full_certification(approval_record_path=str(pending))
    assert g1["full_ready"] is True
    assert g1["level_badges_ok"] is True
    assert g1["certified"] is False
    assert g1["n24_full_conformance"] is False
    assert g1["approval_ok"] is False


def test_full_minimum_covers_all_24():
    assert len(cp.FULL_MINIMUM_IDS) == 24
    cat = cp.load_conformance_catalog()
    by_id = {it["id"]: it for it in (cat.get("items") or [])}
    for iid in cp.FULL_MINIMUM_IDS:
        assert by_id[iid]["status"] == "exists"
