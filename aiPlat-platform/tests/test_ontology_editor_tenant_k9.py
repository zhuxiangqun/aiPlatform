"""N09 K9 — ontology_editor rollback + class CRUD inject resolved tenant."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_DOMAIN = (
    Path(__file__).resolve().parents[1]
    / "apps/ontology_editor/api/domain_crud.py"
).read_text(encoding="utf-8")


def test_domain_crud_source_wires_rollback_and_class_tenant():
    assert "resolve_request_tenant" in _DOMAIN
    assert "rollback_rule_version" in _DOMAIN
    assert "tenant_id=tenant_id" in _DOMAIN
    assert (
        'rule-versions/{version_id}/rollback' in _DOMAIN
        or "rule-versions/{version_id}/rollback" in _DOMAIN
    )
    assert "upsert_ontology_class(" in _DOMAIN
    assert "delete_ontology_class_async(" in _DOMAIN
    assert 'headers.get("X-AIPLAT-TENANT-ID"' not in _DOMAIN


@pytest.mark.asyncio
async def test_rollback_and_class_pass_resolved_tenant(monkeypatch):
    from apps.ontology_editor.api import domain_crud as crud

    captured: dict = {}

    def _fake_tenant(_request):
        return "n09-tenant-k9"

    def _fake_rollback(domain_id, version_id, *, tenant_id="default"):
        captured["rollback"] = {
            "domain_id": domain_id,
            "version_id": version_id,
            "tenant_id": tenant_id,
        }
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "version_id": version_id,
            "status": "rolled_back",
        }

    def _fake_upsert(domain_id, class_name, class_data, *, tenant_id="default"):
        captured["upsert"] = {
            "domain_id": domain_id,
            "class_name": class_name,
            "tenant_id": tenant_id,
        }
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "class_name": class_name,
            "status": "upserted",
        }

    async def _fake_delete(domain_id, class_name, *, tenant_id="default"):
        captured["delete"] = {
            "domain_id": domain_id,
            "class_name": class_name,
            "tenant_id": tenant_id,
        }
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "class_name": class_name,
            "status": "deleted",
        }

    monkeypatch.setattr(crud, "resolve_request_tenant", _fake_tenant)
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "rollback_rule_version", _fake_rollback)
    monkeypatch.setattr(facade, "upsert_ontology_class", _fake_upsert)
    monkeypatch.setattr(facade, "delete_ontology_class_async", _fake_delete)

    req = MagicMock()
    rb = await crud.rollback_rule_version("n09-probe", "42", req)
    assert rb["tenant_id"] == "n09-tenant-k9"
    assert captured["rollback"]["tenant_id"] == "n09-tenant-k9"

    up = await crud.upsert_class(
        "n09-probe", {"class_name": "Thing", "class_data": {"label": "t"}}, req
    )
    assert up["tenant_id"] == "n09-tenant-k9"
    assert captured["upsert"]["tenant_id"] == "n09-tenant-k9"

    deleted = await crud.delete_class("n09-probe", "Thing", req)
    assert deleted["tenant_id"] == "n09-tenant-k9"
    assert captured["delete"]["tenant_id"] == "n09-tenant-k9"


def test_invalidate_domain_caches_loads_tenant_graph(monkeypatch):
    """GraphIndex cache key includes tenant — invalidate must not stay on default."""
    import core.api.core_facade as facade

    loads: list = []

    class _FakeGraph:
        _built = True

    def _fake_load(domain_id, tenant_id="default"):
        loads.append({"domain_id": domain_id, "tenant_id": tenant_id})
        return _FakeGraph()

    class _FakeGI:
        load = staticmethod(_fake_load)

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex",
        _FakeGI,
        raising=False,
    )
    # Patch the import path used inside the function
    import core.harness.ontology_engine.graph_index as gi_mod

    monkeypatch.setattr(gi_mod, "GraphIndex", _FakeGI)

    facade._invalidate_domain_caches("n09-probe", tenant_id="n09-tenant-k9")
    assert loads and loads[-1]["tenant_id"] == "n09-tenant-k9"
