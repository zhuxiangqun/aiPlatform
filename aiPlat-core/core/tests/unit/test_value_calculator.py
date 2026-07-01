"""Unit tests for Business Value Calculator (five-dimension ROI + goals)."""
import pytest
from core.harness.finance.value_calculator import (
    ValueEvent, BusinessGoal, MonthlyValueReport,
    BusinessGoalTracker, ValueCalculator, get_value_calculator,
)


class TestBusinessGoalTracker:

    def test_register_and_get(self):
        tracker = BusinessGoalTracker()
        goal = BusinessGoal(
            goal_id="contract_cycle", description="合同审批周期压缩",
            target_metric="approval_days", baseline_value=5.0, target_value=2.0,
        )
        tracker.register(goal)
        g = tracker.get("contract_cycle")
        assert g is not None
        assert g.description == "合同审批周期压缩"

    def test_update_progress(self):
        tracker = BusinessGoalTracker()
        tracker.register(BusinessGoal(
            goal_id="test_goal", description="test",
            target_metric="days", baseline_value=10.0, target_value=5.0,
        ))
        tracker.update("test_goal", 7.0)
        g = tracker.get("test_goal")
        assert g.progress_pct > 0.5
        assert not g.achieved

    def test_achieved_detection(self):
        tracker = BusinessGoalTracker()
        tracker.register(BusinessGoal(
            goal_id="fast_goal", description="test",
            target_metric="x", baseline_value=0.0, target_value=10.0,
        ))
        tracker.update("fast_goal", 10.0)
        g = tracker.get("fast_goal")
        assert g.achieved

    def test_status_for_routing(self):
        tracker = BusinessGoalTracker()
        tracker.register(BusinessGoal(
            goal_id="lag_goal", description="contract risk reduction",
            target_metric="risk", baseline_value=100.0, target_value=0.0,
        ))
        tracker.update("lag_goal", 90.0)
        status = tracker.get_status_for_routing()
        assert status["has_lagging_goal"]


class TestValueCalculator:

    def test_compute_run_value(self):
        calc = ValueCalculator()
        events = [
            {"input_tokens": 500, "output_tokens": 200},
            {"input_tokens": 300, "output_tokens": 100},
        ]
        v = calc.compute_run_value("run-001", events=events)
        assert v.ai_cost_cny > 0
        assert v.human_equivalent_cost > 0
        assert v.efficiency_saved > 0

    def test_safety_value_from_attacks(self):
        calc = ValueCalculator()
        calc._avg_fine = 50000
        v = calc.compute_run_value("run-002", attacks=3)
        assert v.safety_value >= 150000
        assert v.attacks_blocked == 3

    def test_quality_value_from_pass_rate(self):
        calc = ValueCalculator()
        calc._cost_per_error = 1000
        v = calc.compute_run_value("run-003", pass_rate=0.8)
        assert v.quality_value == 800.0

    def test_translate_three_audiences(self):
        calc = ValueCalculator()
        report = MonthlyValueReport(month="2026-07", tenant_id="test", total_runs=100,
            efficiency={"saved": 5000},
            safety={"value": 10000, "attacks_blocked": 5},
            value_breakdown_pct={"efficiency": 0.3, "safety": 0.5, "quality": 0.2},
        )
        ceo = calc.translate_for(report, "ceo")
        cfo = calc.translate_for(report, "cfo")
        pm = calc.translate_for(report, "pm")
        assert "万" in ceo["hero_number"]
        assert "净节省" in cfo["hero_label"]
        assert pm["hero_label"] == "本月任务数"
        # Different audiences get different keys
        assert ceo.get("breakdown") is not None
        assert cfo.get("detail_rows") is not None

    def test_global_singleton(self):
        c1 = get_value_calculator()
        c2 = get_value_calculator()
        assert c1 is c2


class TestGoalAwareRouter:

    def test_no_tracker_returns_empty(self):
        from core.harness.execution.dynamic_router import GoalAwareRouter
        router = GoalAwareRouter(goal_tracker=None)
        result = router.adjust()
        assert result["context"] == ""

    def test_lagging_goal_triggers_speed(self):
        from core.harness.execution.dynamic_router import GoalAwareRouter
        tracker = BusinessGoalTracker()
        tracker.register(BusinessGoal(
            goal_id="slow", description="test",
            target_metric="x", baseline_value=10.0, target_value=0.0,
        ))
        tracker.update("slow", 9.0)
        router = GoalAwareRouter(goal_tracker=tracker)
        result = router.adjust()
        assert "max_steps" in result["params"]
        assert result["params"]["max_steps"] == 10
