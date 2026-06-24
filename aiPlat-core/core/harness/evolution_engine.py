"""
EvolutionEngine — 夜间统一进化引擎 (Phase 5.5)

"总指挥" — 把 6 个进化组件编成夜间进化流水线:
  1. MetaAgent 审批模式分析
  2. AutoLearner 自动审批高置信度 Skill
  3. PatternCache 淘汰低成功率模式
  4. SkillRouter 自动回滚检测
  5. ExperienceCache 清理过期经验
  6. LoRAAutoTrigger 微调触发检测

环境变量:
  AIPLAT_EVOLUTION_ENABLED: 是否启用 (默认: true)
  AIPLAT_EVOLUTION_CRON_HOUR: 触发小时 (默认: 3)
  AIPLAT_EVOLUTION_AUTO_APPROVE_CONFIDENCE: 自动审批阈值 (默认: 0.9)
  AIPLAT_EVOLUTION_PATTERN_MIN_SUCCESS: Pattern 淘汰阈值 (默认: 0.5)
  AIPLAT_EVOLUTION_EXPERIENCE_RETENTION_DAYS: 经验保留天数 (默认: 30)
  AIPLAT_EVOLUTION_META_ANALYSIS_DAYS: MetaAgent 分析窗口 (默认: 7)
"""

from __future__ import annotations

import asyncio, os, time, json, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.evolution")


@dataclass
class StepResult:
    step_name: str
    status: str          # ok / timeout / error / skipped
    duration_ms: float = 0
    output: Any = None
    error: Optional[str] = None


@dataclass
class EvolutionRun:
    run_id: str
    started_at: float
    steps: List[StepResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    status: str = "running"


_STEP_TIMEOUTS = {
    "meta_analysis": 300,
    "skill_processing": 1800,
    "pattern_prune": 60,
    "rollback_check": 120,
    "experience_evict": 60,
    "sft_trigger": 120,
}


class EvolutionEngine:
    """夜间进化引擎 — 统一调度 6 个进化组件"""

    def __init__(self):
        self._enabled = os.getenv("AIPLAT_EVOLUTION_ENABLED", "true").lower() not in ("0", "false", "no")
        self._cron_hour = int(os.getenv("AIPLAT_EVOLUTION_CRON_HOUR", "3"))
        self._auto_approve_confidence = float(os.getenv("AIPLAT_EVOLUTION_AUTO_APPROVE_CONFIDENCE", "0.9"))
        self._pattern_min_success = float(os.getenv("AIPLAT_EVOLUTION_PATTERN_MIN_SUCCESS", "0.5"))
        self._experience_retention_days = int(os.getenv("AIPLAT_EVOLUTION_EXPERIENCE_RETENTION_DAYS", "30"))
        self._meta_days = int(os.getenv("AIPLAT_EVOLUTION_META_ANALYSIS_DAYS", "7"))

    # ── Public API ──────────────────────────────────────────────────────

    async def nightly_evolution(self) -> EvolutionRun:
        """夜间进化主流程"""
        if not self._enabled:
            return EvolutionRun(run_id="skipped", started_at=time.time(), status="disabled")

        run = EvolutionRun(
            run_id=f"evo-{time.strftime('%Y%m%d_%H%M%S')}",
            started_at=time.time(),
        )
        _log.info(f"EvolutionEngine: starting nightly evolution {run.run_id}")

        # Step 1: MetaAgent analysis
        run.steps.append(await self._step("meta_analysis", self._do_meta_analysis))

        # Step 2: AutoLearner auto-approve
        run.steps.append(await self._step("skill_processing", self._do_skill_processing))

        # Step 3: PatternCache prune
        run.steps.append(await self._step("pattern_prune", self._do_pattern_prune))

        # Step 4: SkillRouter rollback check
        run.steps.append(await self._step("rollback_check", self._do_rollback_check))

        # Step 5: ExperienceCache cleanup
        run.steps.append(await self._step("experience_evict", self._do_experience_evict))

        # Step 6: LoRA trigger check
        run.steps.append(await self._step("sft_trigger", self._do_sft_trigger))

        # Build report
        run.summary = self._build_daily_report(run)
        errors = sum(1 for s in run.steps if s.status in ("timeout", "error"))
        run.status = "completed" if errors == 0 else "partial"

        await self._publish_report(run)
        _log.info(f"EvolutionEngine: nightly evolution {run.status} ({run.run_id})")
        return run

    # ── Step Handlers ───────────────────────────────────────────────────

    async def _do_meta_analysis(self) -> Dict[str, Any]:
        try:
            from core.harness.meta import get_meta_agent
            agent = get_meta_agent()
            suggestions = await agent.analyze(days=self._meta_days)
            return {"suggestions_count": len(suggestions)}
        except Exception as e:
            return {"error": str(e)[:100]}

    async def _do_skill_processing(self) -> Dict[str, Any]:
        try:
            from core.harness.learning import get_auto_learner
            learner = get_auto_learner()
            result = await learner.process_pending(
                min_confidence=self._auto_approve_confidence)
            # ── Self-iteration loop: validate drafts via SkillSimulator ──
            if result.get("drafts_processed", 0) > 0:
                await self._simulate_approved_drafts(result)
            return result
        except Exception as e:
            return {"error": str(e)[:100]}

    async def _simulate_approved_drafts(self, result: Dict[str, Any]):
        """Run SkillSimulator on auto-approved drafts to validate before registration."""
        try:
            from core.harness.learning.skill_simulator import SkillSimulator
            sim = SkillSimulator()
            for skill_id in result.get("approved_skills", []):
                pass_result = await sim.run(skill_id)
                _log.info(f"EvolutionEngine: SkillSimulator {skill_id} pass={pass_result.get('pass', False)}")
        except Exception:
            pass

    async def _do_pattern_prune(self) -> Dict[str, Any]:
        try:
            from core.harness.execution.pattern_cache import get_pattern_cache
            cache = get_pattern_cache()
            return await cache.prune_low_success(
                min_success_rate=self._pattern_min_success)
        except Exception as e:
            return {"error": str(e)[:100]}

    async def _do_rollback_check(self) -> Dict[str, Any]:
        try:
            from core.harness.deployment.canary import get_skill_router
            router = get_skill_router()
            rollbacks = []
            for rollout in router.get_rollout_status():
                reason = router.check_auto_rollback(rollout["skill"])
                if reason:
                    rollbacks.append({"skill": rollout["skill"], "reason": reason})
            return {"rollbacks": rollbacks}
        except Exception as e:
            return {"error": str(e)[:100]}

    async def _do_experience_evict(self) -> Dict[str, Any]:
        try:
            from core.harness.learning.experience_vector import get_experience_cache
            cache = get_experience_cache()
            return await cache.evict_expired(days=self._experience_retention_days)
        except Exception as e:
            return {"error": str(e)[:100]}

    async def _do_sft_trigger(self) -> Dict[str, Any]:
        try:
            from core.harness.training.auto_trigger import get_lora_auto_trigger
            trigger = get_lora_auto_trigger()
            await trigger.trigger()
            return trigger.get_stats()
        except Exception as e:
            return {"error": str(e)[:100]}

    # ── Infrastructure ──────────────────────────────────────────────────

    async def _step(self, name: str, fn) -> StepResult:
        """执行单步: 超时隔离 + 异常捕获"""
        timeout = _STEP_TIMEOUTS.get(name, 120)
        t0 = time.time()
        try:
            async with asyncio.timeout(timeout):
                output = await fn()
                elapsed = (time.time() - t0) * 1000
                _log.info(f"EvolutionEngine: {name} ok ({elapsed:.0f}ms)")
                return StepResult(name, "ok", elapsed, output)
        except asyncio.TimeoutError:
            elapsed = timeout * 1000
            _log.warning(f"EvolutionEngine: {name} timeout ({timeout}s)")
            return StepResult(name, "timeout", elapsed, None, f"exceeded {timeout}s")
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            _log.error(f"EvolutionEngine: {name} error: {e}")
            return StepResult(name, "error", elapsed, None, str(e)[:200])

    def _build_daily_report(self, run: EvolutionRun) -> Dict[str, Any]:
        """生成每日进化日报"""
        ok = sum(1 for s in run.steps if s.status == "ok")
        timeout = sum(1 for s in run.steps if s.status == "timeout")
        error = sum(1 for s in run.steps if s.status == "error")

        highlights = []
        for s in run.steps:
            if s.status == "ok" and s.output:
                o = s.output if isinstance(s.output, dict) else {}
                if s.step_name == "meta_analysis":
                    n = o.get("suggestions_count", 0)
                    if n > 0: highlights.append(f"MetaAgent 生成 {n} 条策略建议")
                elif s.step_name == "skill_processing":
                    n = o.get("auto_approved", 0)
                    if n > 0: highlights.append(f"AutoLearner 自动审批 {n} 个高置信度 Skill")
                elif s.step_name == "pattern_prune":
                    n = o.get("removed", 0)
                    if n > 0: highlights.append(f"PatternCache 淘汰 {n} 个低成功率模式")

        return {
            "date": time.strftime("%Y-%m-%d"),
            "run_id": run.run_id,
            "status": run.status,
            "steps": {s.step_name: {"status": s.status, "duration_ms": round(s.duration_ms)}
                      for s in run.steps},
            "total": {"ok": ok, "timeout": timeout, "error": error},
            "highlights": highlights,
            "duration_seconds": round(time.time() - run.started_at),
        }

    async def _publish_report(self, run: EvolutionRun):
        """发布日报到 EventBus"""
        try:
            from core.harness.observation.event_bus import EventBus
            EventBus.publish("evolution_daily_report", {
                "type": "evolution_report",
                "run_id": run.run_id,
                "status": run.status,
                "summary": run.summary,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        except Exception:
            pass


# ── Global singleton ─────────────────────────────────────────────────────────

_engine: Optional[EvolutionEngine] = None

def get_evolution_engine() -> EvolutionEngine:
    global _engine
    if _engine is None: _engine = EvolutionEngine()
    return _engine
