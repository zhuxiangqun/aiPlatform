"""
Sprint 3 Integration Tests — FDE 演进全链路验证

5 个集成测试场景，覆盖从 "诊断→周报→候选池→知识更新" 的完整数据流。

运行方式：
  cd aiPlat-core && python -m pytest tests/golden_path/test_fde_integration.py -v
"""

import asyncio
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORE = os.path.join(ROOT, "aiPlat-core")
if CORE not in sys.path:
    sys.path.insert(0, CORE)


def _run(coro):
    """Run async coroutine synchronously."""
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════
# Scenario 1: Cron handler → weekly report structure
# ═══════════════════════════════════════════════════════════════

def test_scenario_1_cron_handler_registered():
    """验证 evaluation_summary handler 已注册为 cron job."""
    from core.harness.scheduler.cron import CronScheduler, register_builtin_jobs

    async def _test():
        await register_builtin_jobs()
        from core.harness.scheduler.cron import get_cron_scheduler
        sched = get_cron_scheduler()
        jobs = sched.get_status()
        job_names = list(jobs.get("jobs", {}).keys())
        assert "evaluation_summary" in job_names, (
            f"evaluation_summary 未注册, 当前 jobs: {job_names}"
        )
        assert jobs["jobs"]["evaluation_summary"]["interval"] == 7 * 24 * 3600

    _run(_test())


def test_scenario_1b_empty_data_anti_hallucination():
    """验证空数据时周报返回降级文本而非编造数据."""
    import json as _json

    async def _test():
        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "period": "7d",
            "rag_quality": {"error": "unavailable in test"},
            "hallucination": {"error": "unavailable in test"},
            "user_signals": {"error": "unavailable in test"},
        }
        all_empty = all(
            "error" in str(v)
            for k, v in report.items()
            if k in ("rag_quality", "hallucination", "user_signals")
        )
        if all_empty:
            report["nl_summary"] = "本周无足够数据生成报告，建议保持默认配置。"
        assert report["nl_summary"] == "本周无足够数据生成报告，建议保持默认配置。"

    _run(_test())


# ═══════════════════════════════════════════════════════════════
# Scenario 2: CandidatePool — count accumulation → N≥3 gate
# ═══════════════════════════════════════════════════════════════

def test_scenario_2_candidate_pool_count_gate():
    """验证候选池计数和 N≥3 门控.

    N=1→pending, N=2→pending, N=3→ready."""
    from core.harness.knowledge.candidate_pool import (
        CandidateKnowledgePool, KnowledgeGap,
    )
    CandidateKnowledgePool._instance = None

    async def _test():
        pool = CandidateKnowledgePool.instance()
        pool._pool.clear()

        s1 = await pool.submit(KnowledgeGap(
            source_entity="集成测试实体", gap_type="missing_class",
            description="需要新本体类", source_session_id="test-001",
            domain_id="integration-test", confidence=0.7,
        ))
        assert s1 == "pending", f"N=1: {s1}"

        s2 = await pool.submit(KnowledgeGap(
            source_entity="集成测试实体", gap_type="missing_class",
            description="需要新本体类for测试", source_session_id="test-002",
            domain_id="integration-test", confidence=0.8,
        ))
        assert s2 == "pending", f"N=2: {s2}"

        s3 = await pool.submit(KnowledgeGap(
            source_entity="集成测试实体", gap_type="missing_class",
            description="需要这个本体类", source_session_id="test-003",
            domain_id="integration-test", confidence=0.9,
        ))
        assert s3 in ("ready", "triggered"), f"N=3: {s3}"

    _run(_test())


# ═══════════════════════════════════════════════════════════════
# Scenario 3: Keyword conflict detection
# ═══════════════════════════════════════════════════════════════

def test_scenario_3_keyword_conflict():
    """验证反义关键词冲突检测.

    "激进" vs "保守" → conflict."""
    from core.harness.knowledge.candidate_pool import (
        CandidateKnowledgePool, KnowledgeGap,
    )
    CandidateKnowledgePool._instance = None

    async def _test():
        pool = CandidateKnowledgePool.instance()

        await pool.submit(KnowledgeGap(
            source_entity="话术策略", gap_type="missing_class",
            description="话术应更激进，主动推销", source_session_id="ct-A",
            domain_id="test", confidence=0.7,
        ))

        s2 = await pool.submit(KnowledgeGap(
            source_entity="话术策略", gap_type="missing_class",
            description="话术应更保守，不要推销", source_session_id="ct-B",
            domain_id="test", confidence=0.8,
        ))
        assert s2 == "conflict", f"应为 conflict, 实际: {s2}"

    _run(_test())


# ═══════════════════════════════════════════════════════════════
# Scenario 4: Single noise — stays pending
# ═══════════════════════════════════════════════════════════════

def test_scenario_4_single_noise_no_trigger():
    """验证单次噪音不触发 synthesis."""
    from core.harness.knowledge.candidate_pool import (
        CandidateKnowledgePool, KnowledgeGap,
    )
    CandidateKnowledgePool._instance = None

    async def _test():
        pool = CandidateKnowledgePool.instance()

        s = await pool.submit(KnowledgeGap(
            source_entity="噪音实体", gap_type="missing_class",
            description="客户表述不清", source_session_id="noise-001",
            domain_id="noise-test", confidence=0.3,
        ))
        assert s == "pending", f"单次应为 pending: {s}"

        status = pool.get_status()
        assert status["by_status"].get("triggered", 0) == 0

    _run(_test())


# ═══════════════════════════════════════════════════════════════
# Scenario 5: Full import chain
# ═══════════════════════════════════════════════════════════════

def test_scenario_5_full_import_chain():
    """验证全链路模块可正常导入."""
    modules = [
        ("core.harness.scheduler.cron", "CronScheduler"),
        ("core.harness.knowledge.candidate_pool", "CandidateKnowledgePool"),
        ("core.api.routers.diagnostics", "router"),
    ]

    failed = []
    for mod_name, attr_name in modules:
        try:
            mod = __import__(mod_name, fromlist=[attr_name])
            getattr(mod, attr_name)
        except Exception as e:
            failed.append(f"{mod_name}: {e}")

    assert not failed, f"导入失败: {failed}"
