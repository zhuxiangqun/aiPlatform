"""test_cost_budget_wired.py — verify the cost budget controller is wired into production.

Covers:
- cost_for has a production caller (pipeline_engine._run_stage_skill)
- CostBudgetController is re-exported via CoreFacade
- cost calculation + budget enforcement + downgrade decision behave correctly
"""
import os
import pytest

from core.harness.execution.cost_budget import (
    CostBudgetController,
    get_pricing,
    cost_for,
)


def test_cost_for_has_production_caller():
    """cost_for is imported by pipeline_engine.py (non-test caller)."""
    engine = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..",
        "core", "harness", "execution", "pipeline_engine.py"))
    assert os.path.isfile(engine), f"pipeline_engine.py not found at {engine}"
    with open(engine, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "cost_budget" in src and "cost_for" in src


def test_cost_budget_reexported_by_facade():
    from core.api import core_facade
    assert hasattr(core_facade, "CostBudgetController")
    assert hasattr(core_facade, "cost_for")


def test_get_pricing_reuses_existing_cost_tracker():
    """get_pricing delegates to the existing CostTracker (single source)."""
    pricing = get_pricing()
    assert isinstance(pricing, dict)
    # Existing pricing uses {input, output} keys (config/model_pricing.yaml).
    for model, entry in pricing.items():
        assert isinstance(entry, dict)
        assert "input" in entry and "output" in entry


def test_cost_calculation_correct():
    pricing = {"m": {"input": 1.0, "output": 2.0}}  # USD per million
    c = CostBudgetController(pricing=pricing)
    # 1M prompt + 1M completion = 1.0 + 2.0 = 3.0
    assert abs(c.cost_for("m", 1_000_000, 1_000_000) - 3.0) < 1e-9


def test_unknown_model_is_free():
    c = CostBudgetController(pricing={"known": {"input": 1.0, "output": 1.0}})
    assert c.cost_for("unknown", 1_000_000, 1_000_000) == 0.0


def test_budget_enforcement_and_downgrade():
    pricing = {"m": {"input": 1.0, "output": 0.0}}
    c = CostBudgetController(pricing=pricing, max_cost_usd=1.0, cost_priority="balanced")
    c.record("m", 500_000, 0)  # 0.5 USD
    assert not c.over_budget()
    c.record("m", 500_000, 0)  # 1.0 USD total
    assert c.over_budget()
    assert c._should_downgrade()

    # maximize_quality never downgrades even when over budget
    c2 = CostBudgetController(pricing=pricing, max_cost_usd=0.5, cost_priority="maximize_quality")
    c2.record("m", 500_000, 0)  # 0.5 USD
    assert c2.over_budget()
    assert not c2._should_downgrade()


def test_snapshot_shape():
    c = CostBudgetController(pricing={}, max_cost_usd=2.0)
    c.record("m", 0, 0)
    snap = c.snapshot()
    assert "cost_used_usd" in snap
    assert "cost_budget_usd" in snap
    assert "over_budget" in snap
