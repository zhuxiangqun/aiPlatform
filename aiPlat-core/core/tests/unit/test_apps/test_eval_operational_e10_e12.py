"""评测 Operational E10–E12。"""
from __future__ import annotations

import json
from pathlib import Path

from core.apps.eval.service.operational_gates import (
    build_dual_annotator_kappa_report,
    evaluate_eval_operational_bundle,
    evaluate_eval_process_split_authorize,
    evaluate_eval_production_sla_authorize,
)


def test_e10_default_unauthorized(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_PROCESS_SPLIT_AUTHORIZED", "1")
    g = evaluate_eval_process_split_authorize()
    assert g["authorized"] is False
    assert g["env_alone_insufficient"] is True
    assert g["process_split_policy_env_claimed"] is True


def test_e10_e11_with_approval(tmp_path: Path):
    rec = {
        "status": "approved",
        "decision": "authorize",
        "approvers": ["reviewer-non-author"],
        "gate_ids": ["E10", "E11"],
        "scope": "eval-operational E10 E11",
        "sla_ref": "sla://eval-prod-v1",
    }
    p = tmp_path / "appr.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    e10 = evaluate_eval_process_split_authorize(approval_record_path=str(p))
    e11 = evaluate_eval_production_sla_authorize(
        approval_record_path=str(p), sla_ref="sla://eval-prod-v1"
    )
    assert e10["authorized"] is True
    assert e11["authorized"] is True


def test_e12_kappa_report():
    r = build_dual_annotator_kappa_report(
        [(True, True), (True, False), (False, False), (True, True)],
        scope="agent:demo@v1",
    )
    assert r["gate_id"] == "E12"
    assert r["kappa_kind"] == "inter_annotator"
    assert r["n"] == 4
    assert r["inter_annotator_kappa"] is not None
    assert r["accuracy_claim"] is False


def test_bundle_ready_false_without_approval():
    b = evaluate_eval_operational_bundle(
        kappa_pairs=[(True, True), (False, False)]
    )
    assert b["operational_ready"] is False
    assert b["E12"]["n"] == 2
