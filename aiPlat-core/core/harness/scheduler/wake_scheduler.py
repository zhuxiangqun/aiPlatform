"""WakeScheduler — zero-token autonomous wake trigger (A1.4 A1-axis L4→L5 enabler).



Monitors last user interaction and system degradation signals. When idle

beyond threshold (no human prompt), wakes up autonomously:



  1. Checks pending cron jobs (cron_loader)

  2. Generates a Goal from system state (GoalGenerator)

  3. Dispatches to GoalExecutor for autonomous repair/optimization



This is the "wakeAgent" pattern: the system takes initiative without user input.

Disabled by default (AIPLAT_WAKE_ENABLED=false) — safety-first, human opt-in.

"""

# === capability_dependencies (Phase 43: auto-verified) ===

# depends_on:

#   - extension-and-learning:

#       symbols: [GoalGenerator, GoalExecutor]

#   - abstract-goal-decomposition:

#       symbols: [AbstractGoalDecomposer, GoalDependencyGraph]

# === end ===



from __future__ import annotations



import asyncio

import logging

import os

import time

from typing import Optional



logger = logging.getLogger("aiplat.wake")





class WakeScheduler:

    """Background monitor that wakes the system when idle.



    Monitors a shared last-interaction timestamp (updated by sys_llm_generate /

    ReActLoop on each user message). When idle >= threshold, runs a scan-then-act

    cycle: check pending cron → generate improvement goals → execute reversible ones.

    """



    def __init__(

        self,

        *,

        enabled: bool = False,

        idle_minutes: int = 30,

        check_interval_seconds: int = 120,

    ):

        self._enabled = enabled

        self._idle_seconds = idle_minutes * 60

        self._check_interval = check_interval_seconds

        self._last_interaction: float = time.time()

        self._running = False

        self._wake_count = 0



    @property

    def enabled(self) -> bool:

        return self._enabled



    def mark_interaction(self) -> None:

        """Called by ReActLoop / sys_llm_generate on every user message."""

        self._last_interaction = time.time()



    async def start(self):

        if self._running:

            return

        self._running = True

        logger.info("[wake] scheduler started (idle=%ds, interval=%ds, enabled=%s)",

                     self._idle_seconds, self._check_interval, self._enabled)

        while self._running:

            try:

                await asyncio.sleep(self._check_interval)

                if not self._enabled:

                    continue

                idle = time.time() - self._last_interaction

                if idle < self._idle_seconds:

                    continue

                await self._on_wake(idle)

            except asyncio.CancelledError:

                break

            except Exception as e:

                logger.debug("[wake] cycle error: %s", e)



    async def _on_wake(self, idle_seconds: float):

        self._wake_count += 1

        logger.info("[wake] idle %.0fs → wake #%d", idle_seconds, self._wake_count)

        goal_count = 0

        try:

            from core.harness.optimization.goal_generator import get_goal_generator

            goals = get_goal_generator().generate_auto_executable()

            goal_count = len(goals) if goals else 0

            if goals:

                from core.harness.optimization.goal_executor import get_goal_executor

                executor = get_goal_executor()

                for goal in goals[:2]:  # max 2 per wake cycle

                    success = await executor.execute_goal(goal)

                    logger.info("[wake] executed goal=%s type=%s success=%s",

                                goal.goal_id[:12], goal.goal_type.value, success)



            # Phase 39: abstract goal decomposition path

            await self._try_decompose_pending()



            # PR: Gateway push — notify after idle wake cycle

            try:

                from core.gateway import get_enterprise_gateway

                gw = get_enterprise_gateway()

                await gw.send_message("system",

                    f"[wake] idle {idle_seconds:.0f}s → goals={goal_count}, "

                    f"wake #{self._wake_count}")

            except Exception:

                logging.getLogger(__name__).debug('_on_wake failed', exc_info=True)


        except Exception as e:

            logger.debug("[wake] dispatch failed: %s", e)



    async def _try_decompose_pending(self) -> None:

        """Phase 39: Check for pending abstract goals and decompose them.



        Reads ~/.aiplat/goals/pending/*.json and calls AbstractGoalDecomposer

        to produce sub-goals, then registers them in GoalDependencyGraph and

        executes the first available layer.

        """

        import os as _os_module

        pending_dir = _os_module.path.expanduser("~/.aiplat/goals/pending")

        if not _os_module.path.isdir(pending_dir):

            return



        try:

            from core.harness.optimization.abstract_goal_decomposer import get_abstract_goal_decomposer

            decomposer = get_abstract_goal_decomposer()

            if not decomposer.enabled:

                return

        except Exception as e:

            logger.debug("[wake] decomposer not available: %s", e)

            return



        try:

            entries = sorted(

                _os_module.listdir(pending_dir),

                key=lambda n: _os_module.path.getmtime(

                    _os_module.path.join(pending_dir, n)

                ),

            )

        except Exception:

            return



        processed = 0

        for entry in entries[:1]:  # max 1 per wake cycle to limit LLM cost

            if not entry.endswith(".json"):

                continue

            fp = _os_module.path.join(pending_dir, entry)

            try:

                import json as _json_module

                with open(fp, encoding="utf-8") as f:

                    obj = _json_module.load(f)

            except Exception:

                continue

            if not isinstance(obj, dict):

                continue

            text = obj.get("text", "")

            if not text:

                continue

            domain_id = obj.get("domain_id", "")



            result = await decomposer.decompose(text, domain_id=domain_id or None)

            if not result.sub_goals:

                logger.info(

                    "[wake] decompose: '%s' → 0 sub-goals (feasibility=%.2f)",

                    text[:40], result.feasibility,

                )

                continue



            from core.harness.optimization.goal_dependency_graph import get_goal_dependency_graph

            dep_graph = get_goal_dependency_graph()

            for sg in result.sub_goals:

                dep_graph.add_goal(sg)



            await dep_graph.infer_dependencies(result.sub_goals)

            plan = dep_graph.compute_execution_order()



            logger.info(

                "[wake] decompose: '%s' → %d sub-goals, %d layers (feasibility=%.2f)",

                text[:40], len(result.sub_goals), len(plan.layers), result.feasibility,

            )



            from core.harness.optimization.goal_executor import get_goal_executor

            executor = get_goal_executor()

            for layer in plan.layers[:2]:

                import asyncio as _asyncio_module

                batch = await _asyncio_module.gather(*[

                    executor.execute_goal(g) for g in layer

                ], return_exceptions=True)

                for i, ok in enumerate(batch):

                    if ok is True:

                        dep_graph.mark_completed(layer[i].goal_id)

            processed += 1



        if processed:

            logger.info("[wake] decompose: processed %d pending abstract goals", processed)





# Singleton

_wake_scheduler: Optional[WakeScheduler] = None





def get_wake_scheduler() -> WakeScheduler:

    global _wake_scheduler

    if _wake_scheduler is None:

        enabled = os.getenv("AIPLAT_WAKE_ENABLED", "true").lower() in ("1", "true", "yes")  # noqa: config-flag

        idle_min = int(os.getenv("AIPLAT_WAKE_IDLE_MINUTES", "30") or "30")

        _wake_scheduler = WakeScheduler(enabled=enabled, idle_minutes=idle_min)

    return _wake_scheduler

