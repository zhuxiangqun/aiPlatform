"""N09 K8 — ontology_editor publish/list_rule_versions inject resolved tenant."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_DOMAIN = (
    Path(__file__).resolve().parents[1]
    / "apps/ontology_editor/api/domain_crud.py"
).read_text(encoding="utf-8")


def test_domain_crud_source_uses_resolve_request_tenant():
    assert "resolve_request_tenant" in _DOMAIN
    assert "publish_ontology_domain(domain_id, tenant_id=tenant_id)" in _DOMAIN
    assert "list_rule_versions(domain_id, tenant_id=tenant_id)" in _DOMAIN
    # 禁止裸读 spoofable header
    assert 'headers.get("X-AIPLAT-TENANT-ID"' not in _DOMAIN


def test_resolve_request_tenant_ignores_spoofed_header(monkeypatch):
    monkeypatch.delenv("AIPLAT_PLATFORM_DEV_MODE", raising=False)
    monkeypatch.delenv("AIPLAT_PLATFORM_IDENTITY_SECRET", raising=False)
    from auth.request_identity import resolve_request_tenant

    req = SimpleNamespace(
        headers={
            "X-AIPLAT-TENANT-ID": "victim",
            "X-AIPLAT-ACTOR-ID": "admin",
        }
    )
    assert resolve_request_tenant(req) == "default"


@pytest.mark.asyncio
async def test_publish_and_list_pass_resolved_tenant(monkeypatch):
    from apps.ontology_editor.api import domain_crud as crud

    captured: dict = {}

    def _fake_tenant(_request):
        return "n09-tenant-k8"

    def _fake_publish(domain_id, *, tenant_id="default"):
        captured["publish"] = {"domain_id": domain_id, "tenant_id": tenant_id}
        return {
            "domain_id": domain_id,
            "tenant_id": tenant_id,
            "status": "published",
            "version": "0",
            "class_count": 0,
        }

    def _fake_list(domain_id, *, tenant_id="default"):
        captured["list"] = {"domain_id": domain_id, "tenant_id": tenant_id}
        return [{"id": 1, "label": "n09"}]

    monkeypatch.setattr(crud, "resolve_request_tenant", _fake_tenant)
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "publish_ontology_domain", _fake_publish)
    monkeypatch.setattr(facade, "list_rule_versions", _fake_list)

    req = MagicMock()
    pub = await crud.publish_domain("n09-probe", req)
    assert pub["tenant_id"] == "n09-tenant-k8"
    assert captured["publish"]["tenant_id"] == "n09-tenant-k8"

    listed = await crud.list_rule_versions("n09-probe", req)
    assert listed["tenant_id"] == "n09-tenant-k8"
    assert captured["list"]["tenant_id"] == "n09-tenant-k8"
