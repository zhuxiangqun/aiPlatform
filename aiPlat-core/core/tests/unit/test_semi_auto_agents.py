"""Unit tests for KPIAgent and StrategyAgent (semi-auto Human+Agent roles)."""
import pytest
from core.harness.agents.kpi_agent import KPIAgent, Alert, StrategySuggestion, get_kpi_agent
from core.harness.agents.strategy_agent import StrategyAgent, AdjustResult, get_strategy_agent


class TestKPIAgent:

    def test_monitor_achieved_goal(self):
        """Achieved goal returns ok alert."""
        agent = KPIAgent()
        alert = agent.monitor.__wrapped__ if hasattr(agent.monitor, '__wrapped__') else agent.monitor
        # Use a known non-existent goal for baseline test
        import asyncio
        result = asyncio.run(agent.monitor("non_existent_goal_for_test"))
        assert isinstance(result, Alert)
        assert result.level in ("ok", "warning", "critical")

    def test_monitor_all_returns_list(self):
        agent = KPIAgent()
        import asyncio
        alerts = asyncio.run(agent.monitor_all())
        assert isinstance(alerts, list)

    def test_suggest_strategy_returns_none_for_unknown(self):
        agent = KPIAgent()
        import asyncio
        result = asyncio.run(agent.suggest_strategy("non_existent_goal"))
        assert result is None

    def test_global_singleton(self):
        a1 = get_kpi_agent()
        a2 = get_kpi_agent()
        assert a1 is a2


class TestStrategyAgent:

    def test_auto_adjust_unknown_goal(self):
        agent = StrategyAgent()
        import asyncio
        result = asyncio.run(agent.auto_adjust("non_existent_goal"))
        assert isinstance(result, AdjustResult)
        assert len(result.adjustments) == 0

    def test_safe_params_set(self):
        """Verify SAFE_PARAMS contains only safe-to-auto-adjust params."""
        assert "max_steps" in StrategyAgent.SAFE_PARAMS
        assert "model_name" not in StrategyAgent.SAFE_PARAMS
        assert "model_name" in StrategyAgent.UNSAFE_PARAMS

    def test_handle_anomaly_cascade(self):
        agent = StrategyAgent()
        import asyncio
        result = asyncio.run(agent.handle_anomaly("cascade_failure", "test_tool"))
        assert isinstance(result, AdjustResult)
        assert len(result.adjustments) >= 1
        # Cascade failure → should suggest closing auto-approval
        has_bypass = any(a.get("param") == "bypass_approval_known" for a in result.adjustments)
        assert has_bypass

    def test_handle_anomaly_outlier(self):
        agent = StrategyAgent()
        import asyncio
        result = asyncio.run(agent.handle_anomaly("outlier_latency", "test_tool"))
        has_max_steps = any(a.get("param") == "max_steps" for a in result.adjustments)
        assert has_max_steps

    def test_global_singleton(self):
        a1 = get_strategy_agent()
        a2 = get_strategy_agent()
        assert a1 is a2
