"""Phase C5 — signoff pack is ready; M4 claim stays off."""

from __future__ import annotations

from core.apps.org.service.org_field_ops import field_ops_checklist
from core.apps.org.service.org_runtime import ensure_pilot_goal


def test_c5_pack_ready_without_m4_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ORG_IO_LIVE_UNLOCK", raising=False)
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    ensure_pilot_goal("it-ops")
    cl = field_ops_checklist("it-ops")
    assert cl["m4_claim_allowed"] is False
    assert cl["live"]["live_io_enabled"] is False
    assert cl["c5_pack_ready"] is True
    assert "oncall" in cl["human_pending"]
    assert "live_unlock" in cl["human_pending"]
    by_id = {i["id"]: i for i in cl["items"]}
    assert by_id["signoff_pack"]["ok"] is True
    assert by_id["digital_post"]["ok"] is True
    assert by_id["usage_ledger"]["ok"] is True
    assert by_id["feishu_ingress"]["ok"] is True
    assert by_id["oncall"]["ok"] is False
