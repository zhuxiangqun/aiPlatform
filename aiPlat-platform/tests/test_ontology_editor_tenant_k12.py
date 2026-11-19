"""N09 K12 — monitor process endpoints pass resolved tenant."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_MON = (
    Path(__file__).resolve().parents[1]
    / "apps/ontology_editor/api/monitor_crud.py"
).read_text(encoding="utf-8")


def test_monitor_process_source_wires_tenant():
    assert "resolve_request_tenant" in _MON
    assert "get_process_status(domain_id, process_name or \"\", tenant_id=tenant_id)" in _MON
    assert "get_bottlenecks(domain_id, limit, tenant_id=tenant_id)" in _MON
    assert 'headers.get("X-AIPLAT-TENANT-ID"' not in _MON
    assert "from apps.common_schemas import StatusResponse" in _MON or "StatusResponse" in _MON


@pytest.mark.asyncio
async def test_process_endpoints_pass_resolved_tenant(monkeypatch):
    from apps.ontology_editor.api import monitor_crud as mon

    captured: dict = {}

    def _fake_tenant(_request):
        return "n09-tenant-k12"

    def _fake_status(domain_id, process_name="", *, tenant_id="default"):
        captured["status"] = {"domain_id": domain_id, "tenant_id": tenant_id}
        return [{"id": "1"}]

    def _fake_bot(domain_id, limit=10, *, tenant_id="default"):
        captured["bot"] = {"domain_id": domain_id, "tenant_id": tenant_id}
        return [{"id": "2"}]

    monkeypatch.setattr(mon, "resolve_request_tenant", _fake_tenant)
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "get_process_status", _fake_status)
    monkeypatch.setattr(facade, "get_bottlenecks", _fake_bot)

    req = MagicMock()
    st = await mon.process_status("dom", None, req)
    assert st["tenant_id"] == "n09-tenant-k12"
    assert captured["status"]["tenant_id"] == "n09-tenant-k12"

    bt = await mon.process_bottlenecks("dom", 5, req)
    assert bt["tenant_id"] == "n09-tenant-k12"
    assert captured["bot"]["tenant_id"] == "n09-tenant-k12"
