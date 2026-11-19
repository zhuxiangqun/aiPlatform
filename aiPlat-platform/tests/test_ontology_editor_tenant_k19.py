"""N09 K19 — governance run_cycle / maturity thread tenant into GraphIndex."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_PLATFORM = Path(__file__).resolve().parents[1]
_REPO = _PLATFORM.parent


def test_maturity_and_pipeline_source_wire_tenant():
    mat = (
        _REPO / "aiPlat-core/core/harness/knowledge/domain_maturity.py"
    ).read_text(encoding="utf-8")
    assert "GraphIndex.load(domain_id, tenant_id=tid)" in mat
    assert "AND tenant_id = ?" in mat

    pipe = (
        _REPO / "aiPlat-core/core/harness/knowledge/governance_pipeline.py"
    ).read_text(encoding="utf-8")
    # N09 后续：默认租户走 DomainRouter SSOT
    assert "tenant_id: str = DomainRouter.default_tenant()" in pipe
    assert "compute_domain_maturity(domain_id, tenant_id=tenant_id)" in pipe
    assert "await run_cycle(did, tenant_id=tid)" in pipe

    router = (
        _REPO / "aiPlat-core/core/harness/knowledge/domain_router.py"
    ).read_text(encoding="utf-8")
    assert "refresh_domain_maturity(" in router
    assert "PLATFORM_DEFAULT_TENANT" in router
    assert "compute_domain_maturity(domain_id, tenant_id=tid)" in router


def test_governance_http_passes_tenant_to_run_cycle():
    text = (
        _PLATFORM / "apps/ontology_editor/api/governance_crud.py"
    ).read_text(encoding="utf-8")
    assert "tenant_id=tenant_id" in text
    assert "run_all_domains(tenant_id=tenant_id)" in text


def test_scenario_refresh_passes_tenant():
    text = (
        _PLATFORM / "apps/ontology_editor/api/scenario_crud.py"
    ).read_text(encoding="utf-8")
    assert "refresh_domain_maturity(domain_id, tenant_id=tenant_id)" in text
    assert "compare_domains(tenant_id=tenant_id)" in text


@pytest.mark.asyncio
async def test_run_cycle_http_forwards_tenant(monkeypatch):
    from apps.ontology_editor.api import governance_crud as gov

    captured = {}

    class _R:
        cycle_id = "c1"
        domain_id = "dom"
        overall_health = 90.0
        health_level = "good"
        recommendations = []
        step_results = []

    async def _fake_run(domain_id, *, steps=None, auto_publish=False, tenant_id="default"):
        captured["tenant_id"] = tenant_id
        captured["domain_id"] = domain_id
        return _R()

    monkeypatch.setattr(gov, "resolve_request_tenant", lambda _r: "n09-tenant-k19")
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "run_cycle", _fake_run)

    out = await gov.run_cycle({"domain_id": "dom"}, MagicMock())
    assert out["tenant_id"] == "n09-tenant-k19"
    assert captured["tenant_id"] == "n09-tenant-k19"
