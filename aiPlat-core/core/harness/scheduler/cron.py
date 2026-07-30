"""
CronScheduler — lightweight background task scheduler for self-evolution.

Provides cron-like periodic execution of learning and maintenance jobs.
Uses asyncio for scheduling (no external dependency required).

Jobs:
- failed_runs_analysis: analyze recent failures, generate improvement artifacts
- skill_optimization: scan skill usage stats, suggest consolidations/retires
- evaluation_summary: generate daily/weekly evaluation reports
- pipeline_crystallization: auto-crystallize successful pipelines into skills
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("aiplat.cron")


@dataclass
class CronJob:
    name: str
    interval_seconds: float
    handler: Callable
    description: str = ""
    enabled: bool = True
    last_run: float = 0.0
    run_count: int = 0
    error_count: int = 0


class CronScheduler:
    """Lightweight asyncio-based cron scheduler for self-evolution tasks."""

    def __init__(self):
        self._jobs: Dict[str, CronJob] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register(
        self,
        name: str,
        interval_seconds: float,
        handler: Callable,
        *,
        description: str = "",
        enabled: bool = True,
    ) -> None:
        if interval_seconds < 10:
            raise ValueError("Minimum interval is 10 seconds")
        self._jobs[name] = CronJob(
            name=name,
            interval_seconds=interval_seconds,
            handler=handler,
            description=description,
            enabled=enabled,
        )

    def unregister(self, name: str) -> None:
        self._jobs.pop(name, None)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info(f"CronScheduler started with {len(self._jobs)} jobs")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # noqa: normal-cancellation
        logger.info("CronScheduler stopped")

    async def _loop(self) -> None:
        while self._running:
            now = time.time()
            for job in list(self._jobs.values()):
                if not job.enabled:
                    continue
                if now - job.last_run >= job.interval_seconds:
                    asyncio.ensure_future(self._run_job(job))
                    job.last_run = now
            await asyncio.sleep(1)

    async def _run_job(self, job: CronJob) -> None:
        try:
            logger.debug(f"Cron job starting: {job.name}")
            await job.handler()
            job.run_count += 1
            logger.debug(f"Cron job completed: {job.name} (run #{job.run_count})")
        except Exception as e:
            job.error_count += 1
            logger.warning(f"Cron job failed: {job.name} — {e}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "jobs": {
                name: {
                    "enabled": j.enabled,
                    "interval": j.interval_seconds,
                    "last_run": datetime.fromtimestamp(j.last_run).isoformat() if j.last_run else None,
                    "run_count": j.run_count,
                    "error_count": j.error_count,
                    "description": j.description,
                }
                for name, j in self._jobs.items()
            },
        }


_cron_scheduler: Optional[CronScheduler] = None


def get_cron_scheduler() -> CronScheduler:
    global _cron_scheduler
    if _cron_scheduler is None:
        _cron_scheduler = CronScheduler()
    return _cron_scheduler


async def register_builtin_jobs() -> None:
    """Register built-in cron jobs for self-evolution."""
    sched = get_cron_scheduler()

    async def _failed_runs_analysis():
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        if not store:
            return
        try:
            failed = await store.get_recent_failed_runs(hours=24, limit=50)
            if failed:
                logger.info(f"Failed runs analysis: {len(failed)} runs analyzed")
        except Exception as e:
            logger.debug(f"Failed runs analysis skipped: {e}")

    async def _skill_optimization():
        try:
            from core.harness.integration import get_skill_curator
            curator = get_skill_curator()
            report = await curator.run_if_idle()
            if report and (report.stale_count or report.archived_count or report.merged):
                logger.info(
                    "Curator run complete: active=%d stale=%d archived=%d merged=%d duration=%.1fs",
                    report.active_count, report.stale_count,
                    report.archived_count, len(report.merged),
                    report.duration_seconds,
                )
        except Exception as e:
            logger.debug(f"Skill optimization skipped: {e}")

    sched.register("failed_runs_analysis", 6 * 3600, _failed_runs_analysis,
                   description="Analyze recent failed runs and generate improvement insights")
    sched.register("skill_optimization", 12 * 3600, _skill_optimization,
                   description="Scan skill usage statistics and suggest optimizations")

    # ── evaluation_summary handler ──

    async def _evaluation_summary():
        """Generate weekly evaluation report by aggregating all quality subsystems.
        Writes NL report draft to diagnostics._DIAG_CACHE for frontend consumption.
        
        Known Debt: FDE-specific prompt text should be loaded from
        core/apps/fde/prompts.py once prompt_loader migration is complete.
        """
        import time as _time
        import json as _json

        report = {
            "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "period": "7d",
        }

        # 1. RAG quality dashboard (7d lookback)
        try:
            from core.harness.evaluation.rag_diagnostics_collector import RAGDiagnosticsCollector
            collector = RAGDiagnosticsCollector()
            dash = await collector.collect_quality_dashboard(lookback_hours=168)
            report["rag_quality"] = {
                "avg_faithfulness": dash.hallucination.get("avg_faithfulness", 0),
                "avg_relevancy": dash.hallucination.get("avg_relevancy_proxy", 0),
                "quality_gate_pass_rate": dash.retrieval.get("quality_gate_pass_rate", 0),
                "abandon_rate": dash.signals.get("abandon_rate", 0),
                "repeat_query_rate": dash.signals.get("repeat_query_rate", 0),
                "anomaly_count": len(dash.anomalies),
            }
        except Exception as e:
            report["rag_quality"] = {"error": str(e)[:200]}

        # 2. HallucinationTracker bad cases
        try:
            from core.harness.evaluation.hallucination_tracker import get_hallucination_tracker
            tracker = get_hallucination_tracker()
            recent = tracker.get_recent_reports(limit=50)
            bad_cases = [r for r in recent if r.get("faithfulness", 1) < 0.7]
            report["hallucination"] = {
                "total_reports": len(recent),
                "bad_case_count": len(bad_cases),
                "bad_cases": bad_cases[:10],
            }
        except Exception as e:
            report["hallucination"] = {"error": str(e)[:200]}

        # 3. FeedbackRadar user signal patterns
        try:
            from core.harness.learning.feedback_radar import FeedbackRadar
            radar = FeedbackRadar()
            patterns = await radar.analyze_all_active()
            report["user_signals"] = {
                "pattern_count": sum(len(v) for v in patterns.values()),
                "affected_specs": len(patterns),
                "top_patterns": [
                    {"spec_id": k, "suggestions": [
                        {"type": s.suggestion_type, "severity": s.severity, "detail": s.detail[:200]}
                        for s in v[:3]
                    ]}
                    for k, v in list(patterns.items())[:5]
                ],
            }
        except Exception as e:
            report["user_signals"] = {"error": str(e)[:200]}

        # 4. Generate NL weekly report via LLM
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate

            data_json = _json.dumps(report, ensure_ascii=False, default=str)
            prompt = (
                "你是 AI 评估助。请基于以下数据生成一份本周质量评估报告草稿。"
                # Known Debt: FDE-specific prompt should move to core/apps/fde/prompts.py
                "\n\n数据：\n" + data_json + "\n\n"
                "要求：\n"
                "1. 用中文，分 3-4 段（总览、RAG 质量、幻觉检测、用户信号）\n"
                "2. 每段 2-3 句话，保持客观，不夸大、不美化\n"
                "3. 若某段数据为空、为 0、或仅有 error 字段，写\"本周无足够数据，建议保持默认配置。\"\n"
                "4. 不要编造任何数据，只能基于上述 JSON 中的实际数值\n"
                "5. 末尾标注数据来源：RAGDiagnosticsCollector(168h)、HallucinationTracker、FeedbackRadar"
            )
            nl_report = await sys_llm_generate(
                model=best_model_for_purpose("doc_llm"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                inject_agent_config=False,
            )
            report["nl_summary"] = nl_report
        except Exception as e:
            report["nl_summary"] = f"周报生成暂不可用: {str(e)[:200]}"

        # 5. Write to diagnostics cache for frontend consumption
        try:
            import core.api.routers.diagnostics as diag
            if diag._DIAG_CACHE is None:
                diag._DIAG_CACHE = {}
            diag._DIAG_CACHE["weekly_report"] = report
            diag._DIAG_CACHE_TS = _time.time()
            diag._save_diag_cache()
        except Exception as e:
            logger.warning(f"Weekly report cache write failed: {e}")

        logger.info(
            "evaluation_summary: rag_faithfulness=%s, bad_cases=%d, signal_patterns=%d",
            report.get("rag_quality", {}).get("avg_faithfulness", "N/A"),
            report.get("hallucination", {}).get("bad_case_count", 0),
            report.get("user_signals", {}).get("pattern_count", 0),
        )

    sched.register("evaluation_summary", 7 * 24 * 3600, _evaluation_summary,
                   description="Generate weekly evaluation report from quality subsystems")  # known debt: was FDE-specific


__all__ = [
    "CronScheduler",
    "CronJob",
    "get_cron_scheduler",
    "register_builtin_jobs",
]

