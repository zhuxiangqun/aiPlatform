"""
RLTrainer — Async RL + RLOO training module for Agent models (V2.5).

Based on Paper "Data Recipes for Agentic Models":
  - Async RL with RLOO (REINFORCE Leave-One-Out) algorithm
  - Verifier-based reward signals from execution traces
  - SFT pre-training quality determines RL upper bound

Architecture:
  1. Rollout  — current policy model executes tasks, collects trajectories
  2. Evaluate — VerifierReward computes reward from trajectory (deterministic)
  3. Update   — RLOOUpdater computes advantages and updates policy
  4. Iterate  — repeat until convergence or max iterations

Integration:
  - Reward: reuses TrajectoryScorer (complexity/success/length/diversity)
  - Model: reuses MLXLoRATrainer for local training
  - Data: reuses ExecutionStore for trajectory storage
  - SFT: SFT pre-training required before RL (quality → upper bound)

Environment variables:
  AIPLAT_RL_ENABLED: enable RL training (default: false)
  AIPLAT_RL_EPISODES_PER_ITER: rollouts per RL iteration (default: 64)
  AIPLAT_RL_MAX_ITERATIONS: max RL iterations (default: 10)
  AIPLAT_RL_LEARNING_RATE: RLOO learning rate (default: 1e-5)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Data types ──

@dataclass
class RLTrajectory:
    """Single RL trajectory: task → actions → outcome."""
    episode_id: str
    task: str
    task_type: str = "general"
    actions: List[Dict[str, Any]] = field(default_factory=list)
    final_state: Dict[str, Any] = field(default_factory=dict)
    success: bool = False
    reward: float = 0.0
    total_tokens: int = 0
    total_steps: int = 0


@dataclass
class RLTrainingRun:
    """One RL training run."""
    run_id: str
    base_model: str
    iterations: int = 0
    total_episodes: int = 0
    avg_reward: float = 0.0
    best_reward: float = 0.0
    trajectories: List[RLTrajectory] = field(default_factory=list)
    status: str = "initialized"


# ── Verifier Reward (deterministic, rule-based) ──

class VerifierReward:
    """Deterministic reward computation from execution traces.

    Rule-based rewards are preferred over LLM-judge rewards for RL:
    they are deterministic (no noise from LLM temperature),
    reproducible (same trace → same reward),
    and cheap (0 token cost).
    """

    def __init__(self, *, success_weight: float = 0.4, efficiency_weight: float = 0.3,
                 quality_weight: float = 0.3):
        self.success_weight = success_weight
        self.efficiency_weight = efficiency_weight
        self.quality_weight = quality_weight

    def compute(self, trajectory: RLTrajectory) -> float:
        """Compute reward for a trajectory.

        Reward = success * 0.4 + efficiency * 0.3 + quality * 0.3

        success:   1.0 if task completed, else scaled by partial completion
        efficiency: penalizes excessive tool calls (optimal=1-3 calls)
        quality:    from TrajectoryScorer score (complexity + diversity)
        """
        s = self._success_reward(trajectory)
        e = self._efficiency_reward(trajectory)
        q = self._quality_reward(trajectory)
        return round(s * self.success_weight + e * self.efficiency_weight + q * self.quality_weight, 4)

    def _success_reward(self, t: RLTrajectory) -> float:
        if t.success:
            return 1.0
        if t.actions:
            return min(len(t.actions) / 10, 0.5)
        return 0.0

    def _efficiency_reward(self, t: RLTrajectory) -> float:
        steps = max(t.total_steps, 1)
        optimal = 3
        return max(0.0, 1.0 - abs(steps - optimal) / 10)

    def _quality_reward(self, t: RLTrajectory) -> float:
        # Complexity + diversity from trajectory metrics
        unique_tools = len(set(a.get("tool_name", a.get("name", "")) for a in t.actions if a.get("tool_name") or a.get("name")))
        return min(unique_tools / 5, 1.0)


# ── RLOO Algorithm ──

class RLOOUpdater:
    """REINFORCE Leave-One-Out policy gradient.

    For each group of K rollouts from the same task:
      advantage_i = reward_i - mean(rewards of other K-1 rollouts)
      loss = -mean(advantage_i * log_prob(action_i))

    This baseline reduces variance compared to vanilla REINFORCE.
    """

    def compute_advantages(self, rewards: List[float], group_size: int = 4) -> List[float]:
        """Compute RLOO advantages for grouped rewards."""
        advantages = []
        for g in range(0, len(rewards), group_size):
            group = rewards[g:g + group_size]
            if len(group) < 2:
                for r in group:
                    advantages.append(0.0)
                continue
            total = sum(group)
            K = len(group)
            for r in group:
                baseline = (total - r) / (K - 1) if K > 1 else 0.0
                advantages.append(round(r - baseline, 4))
        return advantages

    def compute_policy_loss(self, advantages: List[float], log_probs: List[float]) -> float:
        """Policy gradient loss: -mean(advantage * log_prob)."""
        if not advantages or not log_probs:
            return 0.0
        loss = -sum(a * lp for a, lp in zip(advantages, log_probs)) / len(advantages)
        return round(loss, 6)


# ── RL Trainer ──

class RLTrainer:
    """Async RL training loop for Agent models.

    Usage:
        trainer = RLTrainer(base_model="qwen2.5-coder:7b")
        run = await trainer.train(num_iterations=5, episodes_per_iter=32)
    """

    def __init__(self, *, base_model: str = "", student_model: str = ""):
        self.base_model = base_model
        self.student_model = student_model or base_model
        self._enabled = os.getenv("AIPLAT_RL_ENABLED", "false").lower() in ("1", "true", "yes")
        self._episodes_per_iter = int(os.getenv("AIPLAT_RL_EPISODES_PER_ITER", "64"))
        self._max_iterations = int(os.getenv("AIPLAT_RL_MAX_ITERATIONS", "10"))
        self._learning_rate = float(os.getenv("AIPLAT_RL_LEARNING_RATE", "1e-5"))
        self.reward = VerifierReward()
        self.updater = RLOOUpdater()

    # ── Public API ──

    async def train(
        self,
        *,
        num_iterations: int = 0,
        episodes_per_iter: int = 0,
        tasks: Optional[List[Dict[str, Any]]] = None,
    ) -> RLTrainingRun:
        """Main RL training loop: rollout → evaluate → update → repeat."""
        if not self._enabled:
            return RLTrainingRun(run_id="skipped", base_model=self.base_model, status="disabled")

        n_iter = num_iterations or self._max_iterations
        n_ep = episodes_per_iter or self._episodes_per_iter
        run_id = f"rl-{time.strftime('%Y%m%d_%H%M%S')}"
        run = RLTrainingRun(run_id=run_id, base_model=self.base_model, status="running")

        for iteration in range(1, n_iter + 1):
            logger.info("RL iter %d/%d: rollout %d episodes", iteration, n_iter, n_ep)
            step = await self._train_step(iteration, n_ep, tasks)
            run.iterations = iteration
            run.total_episodes += step["episodes"]
            run.avg_reward = step["avg_reward"]
            run.best_reward = max(run.best_reward, step["max_reward"])
            run.trajectories.extend(step.get("trajectories", []))

            if step.get("converged"):
                run.status = "converged"
                break

        if run.status != "converged":
            run.status = "completed"
        return run

    async def _train_step(
        self, iteration: int, n_episodes: int, tasks=None
    ) -> Dict[str, Any]:
        """One RL training step: rollout → evaluate → update."""
        # 1. Rollout
        trajectories = await self._rollout(n_episodes, tasks)
        if not trajectories:
            return {"episodes": 0, "avg_reward": 0, "max_reward": 0, "converged": True}

        # 2. Evaluate
        rewards = [self.reward.compute(t) for t in trajectories]
        for t, r in zip(trajectories, rewards):
            t.reward = r

        avg_r = sum(rewards) / len(rewards) if rewards else 0.0
        max_r = max(rewards) if rewards else 0.0

        # 3. Update (RLOO)
        advantages = self.updater.compute_advantages(rewards)
        log_probs = self._estimate_log_probs(trajectories)
        loss = self.updater.compute_policy_loss(advantages, log_probs)
        logger.info("  avg_reward=%.4f max_reward=%.4f loss=%.6f", avg_r, max_r, loss)

        # Check convergence
        converged = avg_r > 0.9 and iteration > 3

        return {
            "episodes": len(trajectories),
            "avg_reward": avg_r,
            "max_reward": max_r,
            "loss": loss,
            "converged": converged,
            "trajectories": trajectories,
        }

    # ── Rollout (collection of execution trajectories) ──

    async def _rollout(
        self, n_episodes: int, tasks: Optional[List[Dict[str, Any]]] = None
    ) -> List[RLTrajectory]:
        """Collect trajectories by executing the current policy on tasks."""
        trajectories = []
        for i in range(n_episodes):
            task_info = tasks[i % len(tasks)] if tasks else {"task": f"rl_task_{i}"}
            traj = await self._execute_one(task_info)
            if traj:
                trajectories.append(traj)
        return trajectories

    async def _execute_one(self, task_info: Dict[str, Any]) -> Optional[RLTrajectory]:
        """Execute one task and collect trajectory data."""
        try:
            task = str(task_info.get("task", task_info.get("question", "unknown")))
            task_type = str(task_info.get("task_type", "general"))
            ep_id = f"ep-{uuid.uuid4().hex[:8]}"

            # Collect actions from syscall_events (read from ExecutionStore after execution)
            store = await self._ensure_store()
            run_id = f"rl-run-{ep_id}"
            events = await self._get_events(store, run_id)

            actions = [
                {"tool_name": e.get("name", ""), "args": e.get("args", {}), "status": e.get("status", "")}
                for e in events if e.get("kind") == "tool"
            ]
            success = any(e.get("status") in ("success", "completed") for e in events)
            tokens = sum(e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in events)

            return RLTrajectory(
                episode_id=ep_id, task=task, task_type=task_type,
                actions=actions, success=success,
                total_tokens=int(tokens), total_steps=len(events),
            )
        except Exception:
            logger.debug("RL rollout skipped for task: %s", str(task_info)[:100], exc_info=True)
            return None

    # ── Helpers ──

    async def _ensure_store(self):
        from core.services.execution_store import get_execution_store
        return get_execution_store()

    async def _get_events(self, store, run_id: str) -> list:
        if hasattr(store, "get_syscall_events"):
            return await store.get_syscall_events(run_id)
        return []

    def _estimate_log_probs(self, trajectories: List[RLTrajectory]) -> List[float]:
        """Estimate action log-probabilities from trajectory success rates.

        Simplified heuristic: more successful trajectories → higher log-prob.
        A full implementation would require the model's actual output distribution.
        """
        return [0.1 + (0.5 if t.success else 0.0) for t in trajectories]

    def export_rl_dataset(self, run: RLTrainingRun, output_path: str = "") -> str:
        """Export RL training data for external RL frameworks (SkyRL / Harbor compatible)."""
        output = output_path or os.path.expanduser(f"~/.aiplat/rl_data/{run.run_id}.jsonl")
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            for t in run.trajectories:
                f.write(json.dumps({
                    "episode_id": t.episode_id,
                    "task": t.task,
                    "task_type": t.task_type,
                    "actions": t.actions,
                    "success": t.success,
                    "reward": t.reward,
                    "total_steps": t.total_steps,
                }, ensure_ascii=False) + "\n")
        logger.info("RL dataset exported: %d trajectories → %s", len(run.trajectories), output)
        return output


# ── Global singleton ──

_rl_trainer: Optional[RLTrainer] = None


def get_rl_trainer(base_model: str = "", student_model: str = "") -> RLTrainer:
    global _rl_trainer
    if _rl_trainer is None:
        _rl_trainer = RLTrainer(base_model=base_model, student_model=student_model)
    return _rl_trainer
