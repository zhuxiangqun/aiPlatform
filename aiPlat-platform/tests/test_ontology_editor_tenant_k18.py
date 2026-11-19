"""N09 K18 — metric/scoring/scenario/governance CRUD bind resolve_request_tenant."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_PLATFORM = Path(__file__).resolve().parents[1]
_REPO = _PLATFORM.parent
_ROOT = _PLATFORM / "apps/ontology_editor/api"


def _src(name: str) -> str:
    return (_ROOT / name).read_text(encoding="utf-8")


def test_metric_scoring_scenario_governance_source_wires_tenant():
    for fn in (
        "metric_crud.py",
        "scoring_crud.py",
        "scenario_crud.py",
        "governance_crud.py",
    ):
        text = _src(fn)
        assert "resolve_request_tenant" in text, fn
        assert 'headers.get("X-AIPLAT-TENANT-ID"' not in text, fn
        assert "from apps.common_schemas import StatusResponse" in text, fn


def test_scoring_engine_source_loads_tenant_graph():
    import re

    text = (
        _REPO / "aiPlat-core/core/harness/knowledge/scoring_engine.py"
    ).read_text(encoding="utf-8")
    loads = re.findall(r"GraphIndex\.load\(([^)]*)\)", text)
    assert loads
    assert all("tenant_id" in args for args in loads)


def test_metric_engine_source_filters_tenant_sql():
    text = (
        _REPO / "aiPlat-core/core/harness/knowledge/metric_engine.py"
    ).read_text(encoding="utf-8")
    assert "tenant_id = ?" in text
    # N09 后续：默认租户走 DomainRouter SSOT，禁止字面量 "default"
    assert "DomainRouter.default_tenant()" in text


@pytest.mark.asyncio
async def test_metric_value_passes_resolved_tenant(monkeypatch):
    from apps.ontology_editor.api import metric_crud as metrics

    captured = {}

    def _fake_tenant(_request):
        return "n09-tenant-k18"

    def _fake_schema(_domain_id):
        return {"metrics": {"m1": {"label": "M1", "binds_to": "C"}}}

    class _M:
        name = "m1"
        label = "M1"
        binds_to = "C"
        aggregation = "avg"
        unit = ""

    def _fake_compute(metric, domain_id, *, time_window_days=30, tenant_id="default"):
        captured["tenant_id"] = tenant_id
        captured["domain_id"] = domain_id
        return {"metric_name": metric.name, "value": 1.0}

    monkeypatch.setattr(metrics, "resolve_request_tenant", _fake_tenant)
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "get_ontology_domain_schema", _fake_schema)
    monkeypatch.setattr(facade, "load_metrics", lambda _s: [_M()])
    monkeypatch.setattr(facade, "compute", _fake_compute)

    out = await metrics.get_metric_value("dom", "m1", MagicMock(), days=7)
    assert out["tenant_id"] == "n09-tenant-k18"
    assert captured["tenant_id"] == "n09-tenant-k18"


@pytest.mark.asyncio
async def test_scoring_evaluate_passes_resolved_tenant(monkeypatch):
    from apps.ontology_editor.api import scoring_crud as scoring

    captured = {}

    class _Model:
        name = "s1"
        label = "S1"
        binds_to = "C"
        rules = []

    def _fake_eval(entity, model, domain_id, *, tenant_id="default"):
        captured["tenant_id"] = tenant_id
        return SimpleNamespace(
            total_score=1.0,
            level="low",
            action="log",
            rule_scores={},
            details=[],
        )

    monkeypatch.setattr(scoring, "resolve_request_tenant", lambda _r: "n09-score-k18")
    import core.api.core_facade as facade

    monkeypatch.setattr(facade, "get_ontology_domain_schema", lambda _d: {})
    monkeypatch.setattr(facade, "load_models", lambda _s: [_Model()])
    monkeypatch.setattr(facade, "evaluate", _fake_eval)

    out = await scoring.evaluate_entity("dom", "s1", MagicMock(), entity="e1")
    assert out["tenant_id"] == "n09-score-k18"
    assert captured["tenant_id"] == "n09-score-k18"
