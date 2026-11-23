"""Core 可认证路径：level 映射、core_ready、人工批准徽章。"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from core.harness.knowledge_pipeline import conformance_pack as cp


def test_catalog_levels_and_core_minimum():
    cat = cp.load_conformance_catalog()
    items = cat.get("items") or []
    assert len(items) == 24
    levels = {it["id"]: it.get("level") for it in items}
    for cid in cp.CORE_MINIMUM_IDS:
        assert levels.get(cid) == "core", cid
    assert set(cat.get("core_minimum_ids") or []) == set(cp.CORE_MINIMUM_IDS)
    assert cat.get("n09_core_probe_freeze") is True
    assert cat.get("n07_n22_h1_condition_freeze") is True
    assert cat.get("n08_action_policy_freeze") is True
    assert cat.get("n24_unified_audit_freeze") is True
    assert cat.get("slo_telemetry_freeze") is True
    assert cat.get("n01_raw_integrity_freeze") is True
    assert cat.get("n02_object_type_freeze") is True
    assert cat.get("n03_claim_freeze") is True
    assert cat.get("n04_n12_write_rbac_freeze") is True
    assert cat.get("n05_wiki_rebuild_freeze") is True
    assert cat.get("n06_query_gateway_freeze") is True
    assert cat.get("n10_gold_eval_freeze") is True
    assert cat.get("n11_n14_migration_freeze") is True
    assert cat.get("n13_calibration_freeze") is True
    assert cat.get("n17_record_semantics_freeze") is True
    assert cat.get("n18_deployed_rbac_freeze") is True
    assert cat.get("n19_fact_query_audit_freeze") is True
    assert cat.get("n20_constraint_layers_freeze") is True
    assert cat.get("n21_query_abstain_freeze") is True
    assert cat.get("n23_ocs_freeze") is True
    assert cat.get("phase2_sufficient_freeze_complete") is True
    assert not cp.sufficient_freeze_missing(cat)
    core = [it for it in items if it.get("level") == "core"]
    assert all(it.get("status") == "exists" for it in core)


def test_core_ready_gate_passes_without_certifying():
    gate = cp.evaluate_core_ready_gate()
    assert gate["pass"] is True, gate
    assert gate["core_ready"] is True
    assert gate["certified"] is False
    assert gate["pilot_certified"] is False
    assert gate["core_claim"] is False
    assert gate["n09_core_probe_freeze"] is True
    assert gate["n07_n22_h1_condition_freeze"] is True
    assert gate["n08_action_policy_freeze"] is True
    assert gate["n24_unified_audit_freeze"] is True
    assert gate["slo_telemetry_freeze"] is True
    assert gate["n01_raw_integrity_freeze"] is True
    assert gate["n02_object_type_freeze"] is True
    assert gate["n03_claim_freeze"] is True
    assert gate["n04_n12_write_rbac_freeze"] is True
    assert gate["n05_wiki_rebuild_freeze"] is True
    assert gate["n06_query_gateway_freeze"] is True
    assert gate["n10_gold_eval_freeze"] is True
    assert gate["n11_n14_migration_freeze"] is True
    assert gate["n13_calibration_freeze"] is True
    assert gate["n17_record_semantics_freeze"] is True
    assert gate["n18_deployed_rbac_freeze"] is True
    assert gate["n19_fact_query_audit_freeze"] is True
    assert gate["n20_constraint_layers_freeze"] is True
    assert gate["n21_query_abstain_freeze"] is True
    assert gate["n23_ocs_freeze"] is True
    assert gate["phase2_sufficient_freeze_complete"] is True
    assert gate["sufficient_freeze_missing"] == []


def test_pilot_core_cert_requires_approval(tmp_path):
    # 无路径 → 不徽章
    g0 = cp.evaluate_pilot_core_certification()
    assert g0["pilot_certified"] is False
    assert "approval_record_path_required" in g0["issues"]

    # superseded/pending 记录 → 不徽章
    pending = (
        Path(cp._repo_root())
        / "reports/products/knowledge-system/v4.3.1/pilot-core-approval-record.pending.json"
    )
    g1 = cp.evaluate_pilot_core_certification(approval_record_path=str(pending))
    assert g1["core_ready"] is True
    assert g1["pilot_certified"] is False
    assert g1["certified"] is False

    # 仓内已批准记录（非作者 朱鸿林）→ 允许 pilot_certified
    approved = (
        Path(cp._repo_root())
        / "reports/products/knowledge-system/v4.3.1/pilot-core-approval-record.approved.json"
    )
    g2 = cp.evaluate_pilot_core_certification(approval_record_path=str(approved))
    assert g2["pass"] is True, g2
    assert g2["pilot_certified"] is True
    assert g2["core_claim"] is True
    # 全量 certified 仍 false
    assert g2["certified"] is False
    assert g2["n24_full_conformance"] is False

    # 合成记录仍可徽章（回归）
    ok = {
        "standard_version": "4.3.1",
        "scope": "pilot lock-service Core",
        "status": "approved",
        "decision": "conditional",
        "approvers": [
            {"name": "Reviewer A", "role": "Reviewer", "is_author": False},
        ],
        "effective_date": "2026-11-19",
        "exceptions": [],
        "record_id": "test-pilot-core",
    }
    path = tmp_path / "pilot-core-approved.json"
    path.write_text(json.dumps(ok), encoding="utf-8")
    g3 = cp.evaluate_pilot_core_certification(approval_record_path=str(path))
    assert g3["pilot_certified"] is True
    assert g3["certified"] is False


def test_core_ready_fails_when_core_item_partial(tmp_path):
    repo = Path(cp._repo_root())
    ok_ref = "reports/products/knowledge-system/v4.3.1/README.md"
    assert (repo / ok_ref).is_file()
    items = []
    for i in range(1, 25):
        nid = f"N{i:02d}"
        level = "core" if nid in cp.CORE_MINIMUM_IDS else "extended"
        status = "partial" if nid == "N01" else ("exists" if level == "core" else "partial")
        items.append(
            {
                "id": nid,
                "level": level,
                "title": nid,
                "status": status,
                "evidence": [ok_ref],
            }
        )
    cat = {
        "pilot_domain": "pilot-domain",
        "core_minimum_ids": sorted(cp.CORE_MINIMUM_IDS),
        "core_adr_exceptions": [],
        "items": items,
        "certification_slots": [
            {"id": s, "title": s, "path": ok_ref} for s in cp.REQUIRED_CERT_SLOTS
        ],
    }
    path = tmp_path / "core_partial.yaml"
    path.write_text(yaml.dump(cat, allow_unicode=True), encoding="utf-8")
    gate = cp.evaluate_core_ready_gate(catalog_path=str(path))
    assert gate["core_ready"] is False
    assert any("N01:core_not_exists_or_excepted" in x for x in gate["issues"])


def test_core_adr_exception_counts_as_ready(tmp_path):
    repo = Path(cp._repo_root())
    ok_ref = "reports/products/knowledge-system/v4.3.1/README.md"
    items = []
    for i in range(1, 25):
        nid = f"N{i:02d}"
        level = "core" if nid in cp.CORE_MINIMUM_IDS else "extended"
        items.append(
            {
                "id": nid,
                "level": level,
                "title": nid,
                "status": "partial" if nid == "N02" else ("exists" if level == "core" else "missing"),
                "evidence": [ok_ref] if level == "core" else [],
            }
        )
    cat = {
        "pilot_domain": "pilot-domain",
        "core_minimum_ids": sorted(cp.CORE_MINIMUM_IDS),
        "core_adr_exceptions": [{"id": "N02", "until": "2027-01-01"}],
        "items": items,
        "certification_slots": [
            {"id": s, "title": s, "path": ok_ref} for s in cp.REQUIRED_CERT_SLOTS
        ],
    }
    path = tmp_path / "core_exc.yaml"
    path.write_text(yaml.dump(cat, allow_unicode=True), encoding="utf-8")
    gate = cp.evaluate_core_ready_gate(catalog_path=str(path))
    assert gate["core_ready"] is True, gate
    assert gate["pilot_certified"] is False
