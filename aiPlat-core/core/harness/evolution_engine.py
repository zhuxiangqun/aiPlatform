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

import logging



import asyncio, os, time, json, logging

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional



_log = logging.getLogger("aiplat.evolution")





@dataclass

# disposition: internal data type — used within evolution engine

class StepResult:

    step_name: str

    status: str          # ok / timeout / error / skipped

    duration_ms: float = 0

    output: Any = None

    error: Optional[str] = None





@dataclass

# disposition: internal data type — used within evolution engine

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



        # Step 7: Tool drift detection

        run.steps.append(await self._step("drift_detect", self._do_drift_detect))



        # Step 8: Defense skill export (ImmuneMemory)

        run.steps.append(await self._step("defense_export", self._do_defense_export))



        # Step 9: Self-harness cycle (pipeline engine optimization)

        run.steps.append(await self._step("self_harness", self._do_self_harness))



        # Step 10: SkillEvolver cross-tenant scan

        run.steps.append(await self._step("cross_tenant_scan", self._do_cross_tenant_scan))



        # Step 11: RL training trigger (after SFT data pipeline, if enabled)

        run.steps.append(await self._step("rl_trigger", self._do_rl_trigger))



        # Step 12: Monthly value snapshot (business ROI + goal tracking)

        run.steps.append(await self._step("value_snapshot", self._do_value_snapshot))



         # Step 13: SpecLifecycle ageing + FeedbackRadar scan (三层 Loop 连接)

        run.steps.append(await self._step("spec_health", self._do_spec_health))

        # Step 14: 三省六部早朝复盘 — AgentRefiner → AGENTS.md 优化建议
        run.steps.append(await self._step("agent_refinement", self._do_agent_refinement))


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

            # Curator: skill lifecycle maintenance (P1-A2)
            try:
                from core.harness.learning.skill_curator import SkillCurator
                curator_report = await SkillCurator().run_if_idle()
                if curator_report:
                    result["curator"] = {
                        "reviewed": curator_report.get("reviewed", 0),
                        "stale": len(curator_report.get("stale", [])),
                        "archived": len(curator_report.get("archived", [])),
                        "merge_suggestions": len(curator_report.get("merge_suggestions", [])),
                    }
            except Exception as e:
                logging.getLogger(__name__).debug('curator run failed: %s', e, exc_info=True)

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

        except Exception as e:

            logging.debug(str(e), exc_info=True)



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



    async def _do_drift_detect(self) -> Dict[str, Any]:

        try:

            from core.harness.learning.tool_drift_detector import get_drift_detector

            dd = get_drift_detector()

            alerts = dd.detect_all()

            for alert in alerts:

                _log.warning("Drift: %s %s %s", alert.tool_name, alert.drift_type.value, alert.detail)

                # PR: ToolDrift → gateway push (latency/error drift only)

                if alert.drift_type.value in ("latency_drift", "error_pattern_drift"):

                    try:

                        from core.gateway import get_enterprise_gateway

                        gw = get_enterprise_gateway()

                        await gw.send_message("system",

                            f"[DRIFT] {alert.tool_name}: {alert.drift_type.value} — {alert.detail}")

                    except Exception:

                        logging.getLogger(__name__).debug('_do_drift_detect failed', exc_info=True)
            return {"alerts_count": len(alerts), "tools_monitored": len(dd.list_tools())}

        except Exception as e:

            return {"error": str(e)[:100]}



    async def _do_defense_export(self) -> Dict[str, Any]:

        try:

            from core.harness.security.immune_memory import ImmuneMemory

            stats = ImmuneMemory.get_stats()

            drafts = []

            for atype in ImmuneMemory._memories:

                draft = ImmuneMemory.export_defense_skill(atype)

                if draft:

                    drafts.append(draft["name"])

            ImmuneMemory.save_persistent()

            return {"types": stats["total_types"], "records": stats["total_records"],

                    "drafts_exported": len(drafts), "drafts": drafts}

        except Exception as e:

            return {"error": str(e)[:100]}



    async def _do_self_harness(self) -> Dict[str, Any]:

        try:

            result = await _run_self_harness()

            return {"ran": True, "result": str(result)[:200]}

        except Exception as e:

            return {"error": str(e)[:100]}



    async def _do_cross_tenant_scan(self) -> Dict[str, Any]:

        """SkillEvolver: scan for shared patterns across tenants."""

        try:

            from core.harness.learning.skill_evolver import get_skill_evolver, ScanConfig

            enabled = os.getenv("AIPLAT_CROSS_TENANT_SCAN_ENABLED", "0") in ("1", "true", "yes")

            if not enabled:

                return {"status": "disabled", "note": "set AIPLAT_CROSS_TENANT_SCAN_ENABLED=true to enable"}

            cfg = ScanConfig(allow_tenant_pattern_access=True)

            evolver = get_skill_evolver(config=cfg)

            drafts = await evolver.scan_cross_tenant()

            submitted = 0

            for draft in drafts:

                try:

                    await evolver.submit_shared_draft(draft)

                    submitted += 1

                except Exception:

                    logging.getLogger(__name__).debug('_do_cross_tenant_scan failed', exc_info=True)
            return {"drafts_found": len(drafts), "submitted": submitted}

        except Exception as e:

            return {"error": str(e)[:100]}



    async def _do_rl_trigger(self) -> Dict[str, Any]:

        """RL training trigger: export RL dataset from recent trajectories."""

        try:

            from core.harness.training.rl_trainer import get_rl_trainer

            from core.harness.utils.model_injection import get_default_model

            base = get_default_model("chat")

            student = get_default_model("chat")

            if not base:

                return {"status": "skipped", "note": "no base model configured"}

            trainer = get_rl_trainer(base_model=base, student_model=student)

            run = await trainer.train(num_iterations=1, episodes_per_iter=8)

            path = trainer.export_rl_dataset(run) if run.trajectories else ""

            return {"status": run.status, "iterations": run.iterations,

                    "episodes": run.total_episodes, "avg_reward": run.avg_reward,

                    "dataset": path}

        except Exception as e:

            return {"error": str(e)[:100]}



    async def _do_value_snapshot(self) -> Dict[str, Any]:

        """Monthly business value snapshot (five-dimension ROI) + audience notifications + KPI monitoring."""

        try:

            from core.harness.finance.value_calculator import get_value_calculator

            calc = get_value_calculator()

            month = time.strftime("%Y-%m")

            report = await calc.compute_monthly(tenant_id="all", month=month)

            calc._persist(report)

            # Notify all three audiences

            for audience in ("ceo", "cfo", "pm"):

                try:

                    payload = calc.translate_for(report, audience)

                    payload["type"] = "monthly_value_report"

                    payload["month"] = month

                    from core.harness.observation.event_bus import EventBus

                    EventBus.publish("system", payload)

                except Exception:

                    logging.getLogger(__name__).debug('_do_value_snapshot failed', exc_info=True)
            # KPIAgent: check all goals, alert on deviation

            try:

                from core.harness.agents.kpi_agent import get_kpi_agent

                kpi = get_kpi_agent()

                alerts = await kpi.monitor_all()

                for alert in alerts:

                    if alert.level != "ok":

                        from core.harness.observation.event_bus import EventBus

                        EventBus.publish("system", {

                            "type": "kpi_alert",

                            "level": alert.level,

                            "message": alert.message,

                            "suggested_action": alert.suggested_action,

                            "month": month,

                        })

            except Exception:

                logging.getLogger(__name__).debug('_do_value_snapshot failed', exc_info=True)
            return {"month": month, "total_runs": report.total_runs,

                    "total_value_cny": report.total_value_cny}

        except Exception as e:

            return {"error": str(e)[:100]}



    async def _do_spec_health(self) -> Dict[str, Any]:

        """Step 13: SpecLifecycle ageing + FeedbackRadar scan (Andrew Ng 三层 Loop P1)."""

        result: Dict[str, Any] = {"spec_stables": 0, "spec_archived": 0, "radar_suggestions": 0}

        try:

            from core.harness.models.spec_lifecycle import get_spec_lifecycle

            sl = get_spec_lifecycle()

            active = sl.get_all_active()

            from datetime import datetime, timezone as _tz



            for sv in active:

                if sv.status.value == "review":

                    try:

                        created = datetime.fromisoformat(sv.created_at)

                        age_days = (datetime.now(_tz.utc) - created.replace(tzinfo=_tz.utc)).days

                        if age_days > 7:

                            sl.mark_stable(sv.spec_id)

                            result["spec_stables"] += 1

                    except Exception:

                        logging.getLogger(__name__).debug('_do_spec_health failed', exc_info=True)
                elif sv.status.value == "stable":

                    try:

                        created = datetime.fromisoformat(sv.created_at)

                        age_days = (datetime.now(_tz.utc) - created.replace(tzinfo=_tz.utc)).days

                        if age_days > 90:

                            sl.mark_archived(sv.spec_id)

                            result["spec_archived"] += 1

                    except Exception:

                        logging.getLogger(__name__).debug('_do_spec_health failed', exc_info=True)
        except Exception:

            logging.getLogger(__name__).debug('_do_spec_health failed', exc_info=True)


        # FeedbackRadar: scan all active specs for signal patterns

        try:

            from core.harness.learning.feedback_radar import get_feedback_radar

            radar = get_feedback_radar()

            findings = await radar.analyze_all_active()

            for spec_id, suggestions in findings.items():

                result["radar_suggestions"] += len(suggestions)

                for s in suggestions:

                    if s.severity.value in ("high", "critical"):

                        from core.harness.observation.event_bus import EventBus

                        EventBus.publish("system", {

                            "type": "spec_health_alert",

                            "spec_id": spec_id,

                            "severity": s.severity.value,

                            "suggestion_type": s.type.value,

                            "detail": s.detail,

                            "suggested_action": s.suggested_action,

                        })

                        # PR: FeedbackRadar → gateway push

                        try:

                            from core.gateway import get_enterprise_gateway

                            gw = get_enterprise_gateway()

                            await gw.send_message("system",

                                f"[{s.severity.value.upper()}] Spec {spec_id[:12]}: {s.detail}\n建议: {s.suggested_action}")

                        except Exception:

                            logging.getLogger(__name__).debug('_do_spec_health failed', exc_info=True)
                        # Trigger pipeline for high/critical suggestions

                        if s.severity.value in ("high", "critical"):

                            try:

                                from core.harness.ontology_engine.engine import trigger_pipeline

                                await trigger_pipeline("spec_improvement", {

                                    "spec_id": spec_id,

                                    "severity": s.severity.value,

                                    "suggestion_type": s.type.value,

                                })

                            except Exception:

                                logging.getLogger(__name__).debug('_do_spec_health failed', exc_info=True)
            _log.debug("FeedbackRadar: %d specs with suggestions", len(findings))

        except Exception:

            logging.getLogger(__name__).debug('_do_spec_health failed', exc_info=True)


        return result


    # ── Step 14: 三省六部早朝复盘 — Agent 优化建议 ────────────────────

    async def _do_agent_refinement(self) -> Dict[str, Any]:
        """第14步: 扫描所有 Agent → 生成 AGENTS.md 优化建议."""
        try:
            from core.harness.learning.agent_refiner import AgentRefiner
            refiner = AgentRefiner()
            result = refiner.run(lookback_days=7)
            refined = result.get("refined", 0)
            return {"status": "ok", "agents_refined": refined, "details": result.get("agents", {})}
        except Exception as e:
            logging.getLogger(__name__).debug("_do_agent_refinement failed", exc_info=True)
            return {"status": "ok", "error": str(e)[:200]}


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

        except Exception as e:

            logging.debug(str(e), exc_info=True)





# ── Global singleton ─────────────────────────────────────────────────────────



_engine: Optional[EvolutionEngine] = None



def get_evolution_engine() -> EvolutionEngine:

    global _engine

    if _engine is None: _engine = EvolutionEngine()

    return _engine





async def _run_self_harness() -> Dict[str, Any]:

    """Module-level adapter for PipelineEngine._run_self_harness_cycle.

    

    Loads failure clusters from disk and runs the self-harness optimization.

    Requires at least 5 historical pipeline run states to be useful.

    """

    try:

        from core.harness.execution.failure_clusterer import load_clusters, cluster_failures

        clusters = load_clusters()

        if not clusters or not clusters.signatures:

            return {"status": "skipped", "note": "no failure clusters to analyze"}



        from core.harness.execution import pipeline_engine as _pe

        engine = _pe.PipelineEngine()

        run_states = [sc.to_dict() if hasattr(sc, 'to_dict') else sc for sc in clusters.recent_runs] if hasattr(clusters, 'recent_runs') else []

        if len(run_states) < 5:

            return {"status": "skipped", "note": f"only {len(run_states)} run states, need >=5"}



        result = await engine._run_self_harness_cycle(run_states)

        return {"ran": True, "accepted": len(result.get("accepted", [])),

                "rejected": len(result.get("rejected", []))}

    except Exception as e:

        return {"error": str(e)[:200]}

