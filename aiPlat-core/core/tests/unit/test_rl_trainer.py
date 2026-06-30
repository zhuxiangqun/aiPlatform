"""Unit tests for RL Training module (RLOO + VerifierReward + RLTrainer)."""
import pytest
from core.harness.training.rl_trainer import (
    RLTrainer, VerifierReward, RLOOUpdater,
    RLTrajectory, RLTrainingRun, get_rl_trainer,
)


class TestVerifierReward:

    def test_success_weights(self):
        vr = VerifierReward(success_weight=0.4, efficiency_weight=0.3, quality_weight=0.3)
        t = RLTrajectory(
            episode_id="ep1", task="test task", task_type="coding",
            actions=[{"tool_name": "code_apply", "args": {}, "status": "success"}],
            success=True, total_steps=3,
        )
        reward = vr.compute(t)
        assert 0.0 < reward <= 1.0

    def test_failure_low_reward(self):
        vr = VerifierReward()
        t = RLTrajectory(
            episode_id="ep2", task="fail task", task_type="qa",
            actions=[], success=False, total_steps=1,
        )
        reward = vr.compute(t)
        assert reward < 0.5

    def test_deterministic_same_input(self):
        """Same trajectory must produce the same reward every time."""
        vr = VerifierReward()
        t = RLTrajectory(episode_id="ep3", task="test", task_type="general",
                         success=True, total_steps=5)
        r1 = vr.compute(t)
        r2 = vr.compute(t)
        assert r1 == r2


class TestRLOO:

    def test_compute_advantages(self):
        updater = RLOOUpdater()
        rewards = [0.9, 0.3, 0.9, 0.5]
        advantages = updater.compute_advantages(rewards, group_size=4)
        assert len(advantages) == 4
        # Higher-reward items get positive advantage, lower get negative
        assert advantages[0] > 0  # 0.9 > avg of others
        assert advantages[1] < 0  # 0.3 < avg of others

    def test_grouped_advantages(self):
        updater = RLOOUpdater()
        rewards = [0.8, 0.2, 0.7, 0.3, 0.9, 0.1]
        advantages = updater.compute_advantages(rewards, group_size=3)
        assert len(advantages) == 6

    def test_single_item_group(self):
        updater = RLOOUpdater()
        advantages = updater.compute_advantages([0.5], group_size=4)
        assert advantages == [0.0]

    def test_policy_loss(self):
        updater = RLOOUpdater()
        loss = updater.compute_policy_loss([0.3, -0.2, 0.1], [0.8, 0.5, 0.6])
        assert loss != 0.0


class TestRLTrajectory:

    def test_defaults(self):
        t = RLTrajectory(episode_id="ep1", task="test")
        assert t.task_type == "general"
        assert t.success is False
        assert t.reward == 0.0

    def test_full_construction(self):
        t = RLTrajectory(
            episode_id="ep1", task="code review", task_type="coding",
            actions=[{"tool_name": "code_apply"}], success=True,
            reward=0.85, total_tokens=500, total_steps=4,
        )
        assert t.task_type == "coding"
        assert t.reward == 0.85


class TestRLTrainer:

    def test_disabled_by_default(self):
        trainer = RLTrainer(base_model="test-model")
        assert not trainer._enabled

    def test_global_singleton(self):
        t1 = get_rl_trainer(base_model="m1")
        t2 = get_rl_trainer(base_model="m2")
        assert t1 is t2  # singleton

    def test_verifier_defaults(self):
        trainer = RLTrainer()
        assert trainer.reward.success_weight == 0.4
        assert trainer.updater is not None


class TestRLTrainingRun:

    def test_run_defaults(self):
        run = RLTrainingRun(run_id="rl-001", base_model="test")
        assert run.iterations == 0
        assert run.status == "initialized"

    def test_trajectory_accumulation(self):
        run = RLTrainingRun(run_id="rl-002", base_model="test")
        run.trajectories.append(RLTrajectory(episode_id="ep1", task="t1"))
        assert len(run.trajectories) == 1
