"""FDE Operational F10–F11。"""
from __future__ import annotations

import json
from pathlib import Path

from core.apps.fde.service.operational_contracts import (
    evaluate_fde_compose_long_running_authorize,
    evaluate_fde_operational_bundle,
    evaluate_fde_production_process_authorize,
)


def test_f10_f11_default_unauthorized(monkeypatch):
    monkeypatch.setenv("AIPLAT_FDE_OPTIONAL_SPLIT", "1")
    f10 = evaluate_fde_production_process_authorize()
    f11 = evaluate_fde_compose_long_running_authorize()
    assert f10["authorized"] is False
    assert f10["optional_split_env_claimed"] is True
    assert f11["compose_long_running_authorized"] is False


def test_f10_with_approval_f11_needs_adr(tmp_path: Path):
    rec = {
        "status": "approved",
        "approvers": ["fde-reviewer"],
        "gate_ids": ["F10", "F11"],
        "scope": "fde-operational F10 F11",
        # missing adr_ref → F11 still closed
    }
    p = tmp_path / "f.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    assert evaluate_fde_production_process_authorize(approval_record_path=str(p))[
        "authorized"
    ]
    f11 = evaluate_fde_compose_long_running_authorize(approval_record_path=str(p))
    assert f11["authorized"] is False
    assert "adr_ref" in f11["reason"]

    rec["adr_ref"] = "ADR-FDE-COMPOSE-LONG-PENDING"
    p.write_text(json.dumps(rec), encoding="utf-8")
    assert evaluate_fde_compose_long_running_authorize(approval_record_path=str(p))[
        "authorized"
    ]
    assert evaluate_fde_operational_bundle(approval_record_path=str(p))[
        "operational_ready"
    ]
