"""Tests for core modules: context_assembler, team_planner, conditional."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "aiPlat-core"))


class TestContextAssembler:
    def test_import(self):
        from core.harness.assembly.context_assembler import TokenBudgetManager
        assert TokenBudgetManager is not None


class TestTeamPlanner:
    def test_import(self):
        from core.harness.execution.team_planner import recommend_team_stages
        assert callable(recommend_team_stages)


class TestConditional:
    def test_import(self):
        from core.harness.execution.conditional import PipelineCondition
        assert PipelineCondition is not None
        assert hasattr(PipelineCondition, 'phase_check')
        assert hasattr(PipelineCondition, 'debate_converged')
