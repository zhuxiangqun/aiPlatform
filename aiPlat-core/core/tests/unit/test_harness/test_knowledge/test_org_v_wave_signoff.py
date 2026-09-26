"""V3 — customer signoff is a read layer. Pack ready is not a signature."""

from __future__ import annotations

from core.apps.org.service.org_field_ops import customer_signoff_view
from core.apps.org.service.org_runtime import ensure_pilot_goal


def test_signoff_view_has_no_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.delenv("AIPLAT_ORG_IO_LIVE_UNLOCK", raising=False)
    monkeypatch.delenv("AIPLAT_ORG_IO_MODE", raising=False)
    ensure_pilot_goal("it-ops")
    view = customer_signoff_view("it-ops")
    assert view["layer"] == "customer_signoff"
    assert view["c5_pack_ready"] is True
    assert view["m4_claim_allowed"] is False
    assert view["signoff_button"] is False
    assert view["writable"] is False
    assert view["platform_layer"] == "value_dashboard"
