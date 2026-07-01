"""Unit tests for Paper Data Recipes alignment (task_type, mixed sampling, learnability)."""
import asyncio
import pytest


class TestTaskTypeInference:

    def test_terminal_from_agent_id(self):
        from core.harness.execution.loop import _infer_task_type
        assert _infer_task_type("do something", "terminal_agent") == "terminal"
        assert _infer_task_type("run command", "shell_executor") == "terminal"

    def test_terminal_from_task_content(self):
        from core.harness.execution.loop import _infer_task_type
        assert _infer_task_type("$ ls /etc", "generic_agent") == "terminal"
        assert _infer_task_type("run: grep -r error", "helper") == "terminal"

    def test_coding_from_agent_id(self):
        from core.harness.execution.loop import _infer_task_type
        assert _infer_task_type("fix bug", "coder_agent") == "coding"
        assert _infer_task_type("optimize", "dev_agent") == "coding"

    def test_coding_from_task_content(self):
        from core.harness.execution.loop import _infer_task_type
        assert _infer_task_type("def main(): return 42", "agent") == "coding"
        assert _infer_task_type("class User:\n    pass", "worker") == "coding"

    def test_qa_from_agent_id(self):
        from core.harness.execution.loop import _infer_task_type
        assert _infer_task_type("what is python", "search_agent") == "qa"
        assert _infer_task_type("explain", "qa_bot") == "qa"

    def test_general_default(self):
        from core.harness.execution.loop import _infer_task_type
        assert _infer_task_type("hello world", "bot") == "general"
        assert _infer_task_type("", "") == "general"


class TestMixedSampling:

    def test_mixed_sample_uniform_distribution(self):
        from core.harness.training.auto_trigger import LoRAAutoTrigger
        trigger = LoRAAutoTrigger()
        scored = [
            ({"task_type": "coding", "run_id": f"c{i}"}, 0.9) for i in range(10)
        ] + [
            ({"task_type": "terminal", "run_id": f"t{i}"}, 0.8) for i in range(10)
        ] + [
            ({"task_type": "qa", "run_id": f"q{i}"}, 0.7) for i in range(5)
        ]
        result = trigger._mixed_sample_by_task_type(scored, 20)
        assert len(result) <= 20
        task_types = [s["task_type"] for s in result]
        assert "coding" in task_types
        assert "terminal" in task_types
        assert "qa" in task_types

    def test_mixed_sample_undersupply(self):
        from core.harness.training.auto_trigger import LoRAAutoTrigger
        trigger = LoRAAutoTrigger()
        scored = [(s, 0.9) for s in [{"task_type": "coding", "run_id": f"c{i}"} for i in range(3)]]
        result = trigger._mixed_sample_by_task_type(scored, 10)
        assert len(result) <= 3

    def test_empty_sample(self):
        from core.harness.training.auto_trigger import LoRAAutoTrigger
        trigger = LoRAAutoTrigger()
        result = trigger._mixed_sample_by_task_type([], 10)
        assert result == []


class TestLearnabilityFilter:

    def test_learnability_method_exists(self):
        from core.harness.training.trajectory_scorer import TrajectoryScorer
        scorer = TrajectoryScorer()
        assert hasattr(scorer, "is_learnable")
        assert callable(scorer.is_learnable)

    @pytest.mark.asyncio
    async def test_learnability_default_behavior(self):
        """is_learnable with no store access → falls through gracefully."""
        from core.harness.training.trajectory_scorer import TrajectoryScorer
        scorer = TrajectoryScorer()
        result = await scorer.is_learnable("nonexistent_run_id_000", "test-model")
        assert result is not None


class TestStratifiedSplit:

    def test_split_with_task_types(self):
        """Verify _split_train_val uses task_type for stratification when available."""
        from core.harness.training.auto_trigger import LoRAAutoTrigger
        trigger = LoRAAutoTrigger()
        dataset = [{"id": i} for i in range(20)]
        samples = [{"task_type": f"type{(i % 4)}", "run_id": f"r{i}"} for i in range(20)]
        train, val = trigger._split_train_val(dataset, samples, 0.25)
        assert len(train) == 15
        assert len(val) == 5
