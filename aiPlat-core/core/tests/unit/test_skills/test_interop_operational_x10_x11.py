"""外援 Operational X10–X11。"""
from __future__ import annotations

import json
from pathlib import Path

from core.harness.maintenance.interop_operational import (
    bind_supplier_sla,
    evaluate_interop_operational_bundle,
    evaluate_interop_production_authorize,
)


def test_x10_default_false():
    assert evaluate_interop_production_authorize()["authorized"] is False


def test_x11_requires_sla_and_approval(tmp_path: Path):
    bad = bind_supplier_sla(sla_ref="sla://v1")
    assert bad["bound"] is False
    rec = {
        "status": "approved",
        "approvers": ["ops-reviewer"],
        "gate_ids": ["X10", "X11"],
        "scope": "interop-operational",
        "sla_ref": "sla://vendor-a",
        "vendor_id": "vendor-a",
    }
    p = tmp_path / "x.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    x10 = evaluate_interop_production_authorize(approval_record_path=str(p))
    x11 = bind_supplier_sla(approval_record_path=str(p))
    assert x10["authorized"] is True
    assert x11["bound"] is True
    assert x11["sla_ref"] == "sla://vendor-a"
    b = evaluate_interop_operational_bundle(approval_record_path=str(p))
    assert b["operational_ready"] is True
