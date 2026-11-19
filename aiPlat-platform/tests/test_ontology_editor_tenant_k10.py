"""N09 K10 — ontology_editor view write + domain meta inject resolved tenant."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_VIEW = (
    Path(__file__).resolve().parents[1]
    / "apps/ontology_editor/api/view_crud.py"
).read_text(encoding="utf-8")
_DOMAIN = (
    Path(__file__).resolve().parents[1]
    / "apps/ontology_editor/api/domain_crud.py"
).read_text(encoding="utf-8")


def test_view_and_domain_source_wires_tenant():
    assert "resolve_request_tenant" in _VIEW
    assert "upsert_view_for_domain(" in _VIEW
    assert "tenant_id=tenant_id" in _VIEW
    assert 'headers.get("X-AIPLAT-TENANT-ID"' not in _VIEW
    assert "from apps.common_schemas import StatusResponse" in _VIEW
    assert "update_ontology_domain_meta(" in _DOMAIN
    assert "tenant_id=tenant_id" in _DOMAIN


@pytest.mark.asyncio
async def test_view_and_meta_pass_resolved_tenant(monkeypatch):
    from apps.ontology_editor.api import view_crud as views
    from apps.ontology_editor.api import domain_crud as domain

    captured: dict = {}

    def _fake_tenant(_request):
        return "n09-tenant-k10"

    def _fake_upsert(domain_id, role, view_data, *, tenant_id="default"):
        captured["upsert"] = {
            "domain_id": domain_id,
            "role": role,
            "tenant_id": tenant_id,
        }
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "role": role,
            "status": "upserted",
        }

    def _fake_delete(domain_id, role, *, tenant_id="default"):
        captured["delete"] = {
            "domain_id": domain_id,
            "role": role,
            "tenant_id": tenant_id,
        }
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "role": role,
            "status": "deleted",
        }

    def _fake_meta(domain_id, *, name="", description="", version="", namespace="", tenant_id="default"):
        captured["meta"] = {"domain_id": domain_id, "tenant_id": tenant_id}
        return {"id": domain_id, "tenant_id": tenant_id, "status": "updated"}

    monkeypatch.setattr(views, "resolve_request_tenant", _fake_tenant)
    monkeypatch.setattr(domain, "resolve_request_tenant", _fake_tenant)

    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "upsert_view_for_domain", _fake_upsert)
    monkeypatch.setattr(facade, "delete_view_for_domain", _fake_delete)
    monkeypatch.setattr(facade, "update_ontology_domain_meta", _fake_meta)

    req = MagicMock()
    up = await views.upsert_view(
        "n09-probe", {"role": "ops", "view": {"label": "Ops"}}, req
    )
    assert up["tenant_id"] == "n09-tenant-k10"
    assert captured["upsert"]["tenant_id"] == "n09-tenant-k10"

    deleted = await views.delete_view("n09-probe", "ops", req)
    assert deleted["tenant_id"] == "n09-tenant-k10"
    assert captured["delete"]["tenant_id"] == "n09-tenant-k10"

    meta = await domain.update_domain_meta("n09-probe", {"name": "Probe"}, req)
    assert meta["tenant_id"] == "n09-tenant-k10"
    assert captured["meta"]["tenant_id"] == "n09-tenant-k10"
