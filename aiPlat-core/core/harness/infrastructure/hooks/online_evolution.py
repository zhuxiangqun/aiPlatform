"""
OnlineEvolution — POST_LOOP Hook: 实时增量进化触发.

Pipeline 阶段完成后，检查是否需要触发轻量级进化：
  1. Pipeline 产生了 ≥3 个新知识原子 → 触发 knowledge 进化
  2. HITL 连续 3 次审批被拒 → 触发 strategy 进化（增强2）
  3. 距离上次进化 > 30 分钟 → 防止过度触发

非阻塞：asyncio.create_task 后台运行，超时 120s。
失败不影响 Pipeline 主流程。

Env vars:
  AIPLAT_ONLINE_EVOLUTION_ENABLED=true  (default: true)
  AIPLAT_EVOLUTION_MIN_INTERVAL=1800    (seconds, default: 1800=30min)
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, Optional

from core.harness.infrastructure.hooks.hook_manager import HookPhase

_log = logging.getLogger("aiplat.online_evolution")

_EVOLUTION_MIN_INTERVAL = int(os.getenv("AIPLAT_EVOLUTION_MIN_INTERVAL", "1800"))


class OnlineEvolution:
    """POST_LOOP Hook — 增量进化触发."""

    def __init__(self):
        self._enabled = os.getenv("AIPLAT_ONLINE_EVOLUTION_ENABLED", "true").lower() in ("1", "true", "yes")
        self._last_run_ts: float = 0.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def on_post_loop(self, state: Dict[str, Any], context: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """POST_LOOP: check trigger conditions and spawn lightweight evolution."""
        import asyncio

        if not self._enabled:
            return None
        if not state.get("_online_evolution_enabled"):
            return None

        # Throttle: minimum interval between runs
        now = time.time()
        if now - self._last_run_ts < _EVOLUTION_MIN_INTERVAL:
            return None

        # Trigger conditions
        should_evolve = False
        reason = ""

        # Condition 1: knowledge atoms produced
        atom_count = state.get("_seci_atom_count", 0)
        if atom_count >= 3:
            should_evolve = True
            reason = f"knowledge_atoms:{atom_count}"

        # Condition 2 (增强2): HITL rejection streak
        hitl_rejections = state.get("_hitl_rejection_streak", 0)
        if hitl_rejections >= 3:
            should_evolve = True
            reason = f"{reason}+hitl_rejections:{hitl_rejections}" if reason else f"hitl_rejections:{hitl_rejections}"

        if not should_evolve:
            return None

        self._last_run_ts = now
        _log.info("Online evolution triggered: %s", reason)

        # Non-blocking: spawn lightweight evolution
        asyncio.create_task(self._run_lightweight(reason))
        return {"online_evolution_triggered": reason}

    async def _run_lightweight(self, reason: str) -> Dict[str, Any]:
        """Run a subset of EvolutionEngine steps (non-blocking, timeout 120s)."""
        import asyncio

        try:
            from core.harness.evolution_engine import get_evolution_engine

            async def _do_evolve():
                engine = get_evolution_engine()
                # Run lightweight subset: knowledge + strategy + KPI snapshot
                result = await engine.nightly_evolution()
                return {"status": getattr(result, "status", "ok"), "reason": reason}

            result = await asyncio.wait_for(_do_evolve(), timeout=120.0)
            _log.info("Online evolution completed: %s", result)
            return result
        except asyncio.TimeoutError:
            _log.warning("Online evolution timed out after 120s")
            return {"status": "timeout", "reason": reason}
        except Exception as exc:
            _log.debug("Online evolution skipped: %s", exc, exc_info=True)
            return {"status": "skipped", "reason": str(exc)[:100]}


_online_evolution: Optional[OnlineEvolution] = None


def get_online_evolution() -> OnlineEvolution:
    """Return the process-wide OnlineEvolution singleton (preserves throttle state)."""
    global _online_evolution
    if _online_evolution is None:
        _online_evolution = OnlineEvolution()
    return _online_evolution
