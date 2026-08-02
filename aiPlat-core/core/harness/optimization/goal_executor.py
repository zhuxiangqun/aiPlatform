"""
Phase 30: GoalExecutor — autonomous closed-loop improvement executor.

Takes improvement proposals from GoalGenerator (Phase 28) and executes
low-risk proposals without human intervention, closing the L5 autonomy gap.

Safety design (risk matrix):
  strategy_optimize  → auto-execute (reversible: just change strategy weight)
  exploration_gap    → auto-execute (reversible: just notify tracker)
  knowledge_stale    → manual only   (irreversible: could delete knowledge)
  healing_gap        → manual only   (requires real error trigger)

Execution lifecycle:
  GoalGenerator.generate_auto_executable() → filtered → _execute_goal()
  Each execution is logged and measurable via stats().

Default: auto_execute_enabled=False (safety-first, human opt-in).
"""
# === capability_dependencies (Phase 43: auto-verified) ===
# depends_on:
#   - extension-and-learning:
#       symbols: [GoalGenerator, ToolBootstrapEngine, StrategySearchEngine]
#   - abstract-goal-decomposition:
#       symbols: [AbstractGoalDecomposer, GoalDependencyGraph, GoalProgressEvaluator]
#   - deploy-and-canary:
#       symbols: [DeployEngine]
# === end ===

from __future__ import annotations

import asyncio
import logging
import os as _os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.goal_executor")


@dataclass
class ExecutionRecord:
    goal_id: str
    goal_type: str
    executed_at: float
    success: bool
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "goal_type": self.goal_type,
            "executed_at": self.executed_at,
            "success": self.success,
            "description": self.description,
        }


class GoalExecutor:
    """Periodic autonomous goal executor.

    Usage:
        executor = GoalExecutor(enabled=True, interval_minutes=5)
        executor.start()
        # ... runs in background ...
        executor.stats()  # → {"total_auto_executed": 3, ...}
        executor.stop()
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        interval_minutes: int = 5,
        max_per_scan: int = 2,
    ):
        self._enabled = enabled
        self._interval = interval_minutes * 60
        self._max_per_scan = max_per_scan
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._history: List[ExecutionRecord] = []
        self._last_scan_ts: float = 0.0
        self._bootstrapped: set = set()  # Phase 31 debounce

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info("[goal_executor] %s", "enabled" if value else "disabled")

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "[goal_executor] started (interval=%ds, max_per_scan=%d, enabled=%s)",
            self._interval, self._max_per_scan, self._enabled,
        )

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[goal_executor] stopped (total_executed=%d)", len(self._history))

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                if not self._enabled:
                    continue
                await self._scan_and_execute()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[goal_executor] scan error: %s", e)

    async def _scan_and_execute(self) -> None:
        self._last_scan_ts = time.time()
        try:
            from core.harness.optimization.goal_generator import get_goal_generator
            generator = get_goal_generator()
            goals = generator.generate_auto_executable()
        except Exception as e:
            logger.debug("goal scan failed: %s", e)
            return

        # Phase 39: Count business_objective goals before execution
        bizobj_before = sum(1 for g in goals if g.goal_type.value == "business_objective")

        executed = 0
        for goal in goals[:self._max_per_scan]:
            success = await self._execute_goal(goal)
            executed += 1
            self._history.append(ExecutionRecord(
                goal_id=goal.goal_id,
                goal_type=goal.goal_type.value,
                executed_at=time.time(),
                success=success,
                description=goal.title,
            ))

        if executed:
            logger.info(
                "[goal_executor] scan complete: %d goals, %d executed",
                len(goals), executed,
            )

        # Phase 39: Progress evaluation after business_objective decomposition
        if bizobj_before > 0:
            try:
                from core.harness.optimization.goal_progress_evaluator import get_goal_progress_evaluator
                evaluator = get_goal_progress_evaluator()
                from core.harness.optimization.goal_dependency_graph import get_goal_dependency_graph
                dep_graph = get_goal_dependency_graph()
                gs = dep_graph.stats()
                completed_goals = [
                    g for gid, node in dep_graph._nodes.items()
                    if node.completed
                ]
                report = evaluator.evaluate(
                    abstract_goal="(pending objectives)",
                    completed_sub_goals=[n.goal for gid, n in dep_graph._nodes.items() if n.completed],
                    total_goals=gs["total_goals"],
                )
                logger.info(
                    "[goal_executor] progress: %.0f%% (%d/%d) trend=%s rec=%s",
                    report.completion_rate * 100,
                    report.completed_count, report.total_count,
                    report.trend, report.recommendation,
                )
            except Exception as e:
                logger.debug("[goal_executor] progress eval skipped: %s", e)

    def _has_bootstrapped(self, error_type: str) -> bool:
        """Phase 31: Check if we've already bootstrapped this error type."""
        return error_type in self._bootstrapped

    async def _execute_business_objective(self, goal) -> bool:
        """Phase 39: Decompose an abstract business objective into sub-goals.

        Calls AbstractGoalDecomposer.decompose(), registers sub-goals in
        GoalDependencyGraph, infers dependencies, and executes the first layer.
        """
        evidence = goal.source_evidence
        abstract_text = evidence.get("abstract_goal_text", "")
        domain_id = evidence.get("domain_id", "")
        if not abstract_text:
            logger.debug("[goal_executor] business_objective: no abstract_goal_text")
            return False

        try:
            from core.harness.optimization.abstract_goal_decomposer import get_abstract_goal_decomposer
            decomposer = get_abstract_goal_decomposer()
            if not decomposer.enabled:
                logger.info("[goal_executor] AbstractGoalDecomposer disabled, skip bizobj")
                return False

            result = await decomposer.decompose(abstract_text, domain_id=domain_id or None)
            if not result.sub_goals:
                logger.info(
                    "[goal_executor] business_objective decomposed: 0 sub-goals "
                    "(feasibility=%.2f, missing_caps=%d)",
                    result.feasibility, len(result.missing_capabilities),
                )
                return False

            from core.harness.optimization.goal_dependency_graph import get_goal_dependency_graph
            dep_graph = get_goal_dependency_graph()
            for sg in result.sub_goals:
                dep_graph.add_goal(sg)

            await dep_graph.infer_dependencies(result.sub_goals)
            plan = dep_graph.compute_execution_order()

            logger.info(
                "[goal_executor] business_objective decomposed: "
                "'%s' → %d sub-goals in %d layers (feasibility=%.2f)",
                abstract_text[:40], len(result.sub_goals),
                len(plan.layers), result.feasibility,
            )

            executed = 0
            for layer in plan.layers[:2]:
                batch = await asyncio.gather(*[
                    self._execute_goal(g) for g in layer
                ], return_exceptions=True)
                for i, ok in enumerate(batch):
                    if ok is True:
                        dep_graph.mark_completed(layer[i].goal_id)
                        executed += 1
                    elif isinstance(ok, Exception):
                        logger.warning(
                            "[goal_executor] bizobj sub-goal %s failed: %s",
                            layer[i].goal_id[:12], ok,
                        )

            self._history.append(ExecutionRecord(
                goal_id=goal.goal_id,
                goal_type=goal.goal_type.value,
                executed_at=time.time(),
                success=executed > 0,
                description=f"Decomposed '{abstract_text[:30]}' → {executed} executed",
            ))
            return executed > 0
        except Exception as e:
            logger.warning("[goal_executor] business_objective failed: %s", e)
            return False

    async def execute_goal(self, goal) -> bool:
        """Execute a single goal ON DEMAND (human-approved path). Records history.

        Unlike the autonomous loop, this does NOT require enabled=True or start();
        it is the entry point for the diagnostics→propose→human-approve→execute
        closed loop. Callers MUST gate this (auto_executable check + opt-in flag).
        """
        success = await self._execute_goal(goal)
        self._history.append(ExecutionRecord(
            goal_id=goal.goal_id,
            goal_type=goal.goal_type.value,
            executed_at=time.time(),
            success=success,
            description=goal.title,
        ))
        return success

    async def _execute_goal(self, goal) -> bool:
        """Execute a single auto-executable goal. Returns success.

        Phase 39: checks GoalDependencyGraph before execution.
        """
        try:
            # ── Phase 39: dependency check ──
            try:
                from core.harness.optimization.goal_dependency_graph import get_goal_dependency_graph
                dep_graph = get_goal_dependency_graph()
                blocker = dep_graph.check_blocked(goal.goal_id)
                if blocker:
                    logger.debug(
                        "[goal_executor] goal %s blocked by %s, skipping",
                        goal.goal_id[:12], blocker[:12],
                    )
                    return False
            except Exception:
                logging.getLogger(__name__).debug('_execute_goal failed', exc_info=True)

            if goal.goal_type.value == "business_objective":
                return await self._execute_business_objective(goal)

            if goal.goal_type.value == "strategy_optimize":
                # Mark the error_type for active exploration
                evidence = goal.source_evidence
                error_type = evidence.get("error_type", "")
                weak_strategy = evidence.get("strategy", "")
                if error_type:
                    from core.harness.optimization.search_engine import get_search_engine
                    engine = get_search_engine()
                    engine.reset(error_type)  # clear convergence, restart exploration
                    logger.info(
                        "[goal_executor] auto-optimized: %s (%s → restarting search)",
                        error_type, weak_strategy,
                    )
                    self._mark_completed(goal.goal_id)
                    await self._push_to_gateway(f"auto-optimized: {error_type} → search reset ({weak_strategy})")
                    return True

            elif goal.goal_type.value == "exploration_gap":
                evidence = goal.source_evidence
                error_type = evidence.get("error_type", "")
                if error_type:
                    from core.harness.optimization.search_engine import get_search_engine
                    engine = get_search_engine()
                    engine.reset(error_type)
                    logger.info(
                        "[goal_executor] auto-exploring: %s → search reset",
                        error_type,
                    )
                    self._mark_completed(goal.goal_id)
                    await self._push_to_gateway(f"auto-exploring: {error_type} → search reset")
                    return True

            elif goal.goal_type.value == "knowledge_stale":
                # Not auto-executed (irreversible)
                pass

            elif goal.goal_type.value == "healing_gap":
                # Not auto-executed (requires real error trigger)
                pass

            elif goal.goal_type.value == "tool_gap":
                # Phase 31: Auto-bootstrap tools for recurring patterns
                # Debounce: only bootstrap once per session
                evidence = goal.source_evidence
                error_type = evidence.get("error_type", "")
                if error_type and not self._has_bootstrapped(error_type):
                    from core.harness.optimization.tool_bootstrap import get_tool_bootstrap
                    engine = get_tool_bootstrap()
                    safe_name = f"{error_type}_diagnostics"
                    description = f"Automated diagnostic tool for {error_type} errors"
                    result = await engine.bootstrap(
                        capability_name=safe_name,
                        description=description,
                        auto_approve=True,
                    )
                    self._bootstrapped.add(error_type)
                    logger.info(
                        "[goal_executor] bootstrapped tool: %s → %s",
                        safe_name, result.status,
                    )
                    ok = result.status == "registered"
                    if ok:
                        self._mark_completed(goal.goal_id)
                        await self._push_to_gateway(f"auto-bootstrapped tool: {safe_name}")
                        # Phase 40: auto-deploy after successful bootstrap
                        try:
                            from core.harness.deployment.deploy_engine import get_deploy_engine
                            deploy_engine = get_deploy_engine()
                            if deploy_engine.enabled:
                                deploy_result = await deploy_engine.deploy(
                                    safe_name, "v1.0.0",
                                    effects_type=result.effects_type,
                                )
                                logger.info(
                                    "[goal_executor] deployed: %s → %s (canary=%d%%)",
                                    safe_name, deploy_result.status, deploy_result.canary_pct,
                                )
                        except Exception:
                            logging.getLogger(__name__).debug('code failed', exc_info=True)
                    return ok

        except Exception as e:
            logger.warning("[goal_executor] execution failed for %s: %s", goal.goal_id, e)
        return False

    @staticmethod
    def _mark_completed(goal_id: str) -> None:
        """Phase 39: Mark a goal as completed in the dependency graph."""
        try:
            from core.harness.optimization.goal_dependency_graph import get_goal_dependency_graph
            get_goal_dependency_graph().mark_completed(goal_id)
        except Exception:
            logging.getLogger(__name__).debug('_mark_completed failed', exc_info=True)

    def stats(self) -> Dict[str, Any]:
        """Execution statistics."""
        recent = [r.to_dict() for r in self._history[-10:]]
        return {
            "enabled": self._enabled,
            "running": self._running,
            "interval_minutes": self._interval // 60,
            "max_per_scan": self._max_per_scan,
            "total_auto_executed": len(self._history),
            "last_scan_ts": self._last_scan_ts,
            "last_scan_age_seconds": round(time.time() - self._last_scan_ts, 1) if self._last_scan_ts else -1,
            "recent_executions": recent,
        }

    async def _push_to_gateway(self, message: str) -> None:
        """Push auto-execution result to enterprise gateway + trigger verification pipeline."""
        try:
            from core.gateway import get_enterprise_gateway
            gw = get_enterprise_gateway()
            await gw.send_message("system", f"[goal-executor] {message}")
        except Exception:
            logging.getLogger(__name__).debug('_push_to_gateway failed', exc_info=True)
        try:
            from core.harness.ontology_engine.engine import trigger_pipeline
            await trigger_pipeline("goal_verification", {"message": message})
        except Exception:
            logging.getLogger(__name__).debug('_push_to_gateway failed', exc_info=True)


# ── Singleton ──

_executor: Optional[GoalExecutor] = None


def get_goal_executor() -> GoalExecutor:
    global _executor
    if _executor is None:
        _executor = GoalExecutor()
    return _executor
