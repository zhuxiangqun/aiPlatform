"""N09 K11 — ontology_editor monitor HTTP injects resolved tenant."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_MONITOR = (
    Path(__file__).resolve().parents[1]
    / "apps/ontology_editor/api/monitor_crud.py"
).read_text(encoding="utf-8")


def test_monitor_source_wires_resolve_request_tenant():
    assert "resolve_request_tenant" in _MONITOR
    assert "get_state_distribution(domain_id, tenant_id=tenant_id)" in _MONITOR
    assert "get_bottleneck_analysis(domain_id, limit, tenant_id=tenant_id)" in _MONITOR
    assert "get_sla_violations(domain_id, tenant_id=tenant_id)" in _MONITOR
    assert "get_trend_data(domain_id, days, tenant_id=tenant_id)" in _MONITOR
    assert "from apps.common_schemas import StatusResponse" in _MONITOR
    assert 'headers.get("X-AIPLAT-TENANT-ID"' not in _MONITOR


@pytest.mark.asyncio
async def test_monitor_endpoints_pass_resolved_tenant(monkeypatch):
    from apps.ontology_editor.api import monitor_crud as mon

    captured: dict = {}

    def _fake_tenant(_request):
        return "n09-tenant-k11"

    def _fake_dist(domain_id, *, tenant_id="default"):
        captured["dist"] = {"domain_id": domain_id, "tenant_id": tenant_id}
        return [{"class_name": "Order", "state_name": "open", "count": 1}]

    def _fake_bn(domain_id, limit=10, *, tenant_id="default"):
        captured["bn"] = {
            "domain_id": domain_id,
            "limit": limit,
            "tenant_id": tenant_id,
        }
        return []

    monkeypatch.setattr(mon, "resolve_request_tenant", _fake_tenant)
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "get_state_distribution", _fake_dist)
    monkeypatch.setattr(facade, "get_bottleneck_analysis", _fake_bn)

    req = MagicMock()
    dist = await mon.state_distribution("n09-probe", req)
    assert dist["tenant_id"] == "n09-tenant-k11"
    assert captured["dist"]["tenant_id"] == "n09-tenant-k11"

    bn = await mon.bottlenecks("n09-probe", req, limit=5)
    assert bn["tenant_id"] == "n09-tenant-k11"
    assert captured["bn"]["tenant_id"] == "n09-tenant-k11"
