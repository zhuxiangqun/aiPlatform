"""P0: graph_validate must never false-pass when checks did not run."""
from __future__ import annotations

import pytest

from core.harness.syscalls.graph_validate import _finalize, sys_graph_validate
from core.harness.ontology_engine.graph_index import GraphIndex
from core.harness.knowledge.ontology_validator import ValidationReport, ValidationItem


@pytest.mark.asyncio
async def test_load_failure_is_error_not_valid(monkeypatch):
    def _boom(cls, domain_id):
        raise RuntimeError("no graph")

    monkeypatch.setattr(GraphIndex, "load", classmethod(_boom))

    result = await sys_graph_validate("lock-service", operation="consistency")
    assert result["valid"] is False
    assert result["status"] == "error"
    assert result["checks_run"] == []


@pytest.mark.asyncio
async def test_validator_failure_is_unchecked_not_green(monkeypatch):
    class _FakeGraph:
        def stats(self):
            return {"nodes": 1, "edges": 1}

        def get_node(self, _eid):
            return None

    monkeypatch.setattr(GraphIndex, "load", classmethod(lambda cls, d: _FakeGraph()))
    monkeypatch.setattr(
        "core.harness.knowledge.ontology_validator.validate_domain",
        lambda domain_id, **kw: (_ for _ in ()).throw(RuntimeError("yaml missing")),
    )

    result = await sys_graph_validate("lock-service", operation="consistency")
    assert result["valid"] is False
    assert result["status"] == "unchecked"
    assert result["checks_run"] == []
    assert any(s["check"] == "domain_graph_vs_yaml" for s in result["skipped_checks"])


@pytest.mark.asyncio
async def test_successful_domain_check_sets_checks_run(monkeypatch):
    class _FakeGraph:
        def stats(self):
            return {"nodes": 2, "edges": 1}

        def get_node(self, _eid):
            return None

    monkeypatch.setattr(GraphIndex, "load", classmethod(lambda cls, d: _FakeGraph()))

    report = ValidationReport(domain_id="lock-service")
    report.add(ValidationItem("orphan_node", "warning", "bad class", entity_name="e1", class_name="X"))

    monkeypatch.setattr(
        "core.harness.knowledge.ontology_validator.validate_domain",
        lambda domain_id, **kw: report,
    )

    result = await sys_graph_validate("lock-service", operation="consistency")
    assert "domain_graph_vs_yaml" in result["checks_run"]
    assert result["status"] == "ok"
    assert result["valid"] is False
    assert len(result["violations"]) >= 1


@pytest.mark.asyncio
async def test_unsupported_operation_unchecked(monkeypatch):
    class _FakeGraph:
        def stats(self):
            return {"nodes": 0, "edges": 0}

    monkeypatch.setattr(GraphIndex, "load", classmethod(lambda cls, d: _FakeGraph()))

    result = await sys_graph_validate("lock-service", operation="not-a-real-op")
    assert result["valid"] is False
    assert result["status"] == "unchecked"
    assert result["checks_run"] == []


def test_finalize_ban_false_pass():
    out = _finalize(
        operation="consistency",
        violations=[],
        suggestions=[],
        checks_run=[],
        skipped_checks=[{"check": "x", "reason": "y"}],
    )
    assert out["valid"] is False
    assert out["status"] == "unchecked"
