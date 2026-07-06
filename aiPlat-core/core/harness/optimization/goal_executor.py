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

from __future__ import annotations

import asyncio
import logging
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

    def _has_bootstrapped(self, error_type: str) -> bool:
        """Phase 31: Check if we've already bootstrapped this error type."""
        return error_type in self._bootstrapped

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
        """Execute a single auto-executable goal. Returns success."""
        try:
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
                    return result.status == "registered"

        except Exception as e:
            logger.warning("[goal_executor] execution failed for %s: %s", goal.goal_id, e)
        return False

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


# ── Singleton ──

_executor: Optional[GoalExecutor] = None


def get_goal_executor() -> GoalExecutor:
    global _executor
    if _executor is None:
        _executor = GoalExecutor()
    return _executor
