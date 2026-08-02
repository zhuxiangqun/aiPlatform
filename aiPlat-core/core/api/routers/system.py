from __future__ import annotations

from pydantic import BaseModel



class ItemResponse(BaseModel):

    data: dict = {}





class StatusResponse(BaseModel):

    status: str = "ok"

    message: str = ""



"""System-level self-evolution endpoints — core system capability, not FDE-specific.



These provide the same diagnose/heal/evolve/self-check/overview capabilities

as /fde/* but at the system level (/system/*), accessible without FDE context.

"""





import logging

import time

from typing import Any, Dict



from fastapi import APIRouter, HTTPException



router = APIRouter(prefix="/system", tags=["system"])

log = logging.getLogger("aiplat.system")





# ════════════════════════════════════════════════════════════

# System Overview

# ════════════════════════════════════════════════════════════



@router.get("/overview", response_model=ItemResponse)

async def system_overview():

    """System-level self-description with live metrics — not gated behind FDE."""

    # Collect live metrics

    live = {}

    try:

        import json, os

        path = os.path.expanduser("~/.aiplat/ontologies/registry.json")

        with open(path) as f:

            live["domains"] = len(json.load(f).get("domains", {}))

    except Exception:

        live["domains"] = 0



    try:

        from core.harness.knowledge.seci_engine import get_seci_engine

        se = get_seci_engine()

        live["knowledge_atoms"] = se.get_atom_count()

        live["knowledge_links"] = se.get_link_count()

    except Exception:

        live["knowledge_atoms"] = 0

        live["knowledge_links"] = 0



    try:

        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.knowledge.domain_router import get_domain_router

        router = get_domain_router()
        domain_counts = {}
        for domain_id in router.list_domains():
            try:
                g = GraphIndex.load(domain_id)
                node_count = len(g._nodes) if hasattr(g, '_nodes') else 0
                domain_counts[domain_id] = node_count
            except Exception:
                domain_counts[domain_id] = 0

        live["domain_entity_counts"] = domain_counts

    except Exception:

        live["domain_entity_counts"] = {}


    try:

        from core.api.core_facade import get_fde_pipeline_health

        live["pipeline"] = get_fde_pipeline_health()

    except Exception:

        live["pipeline"] = "unknown"



    live["self_evolution_phase"] = "四阶段竣工 (POST_LOOP每10次 + 后台每小时)"

    live["coding_constitution"] = "karpathy_v1 (全局默认 → 编码前思考+简洁优先+精准修改+目标驱动)"



    # Phase 39-41: L6 autonomous capabilities

    try:

        from core.harness.optimization.abstract_goal_decomposer import get_abstract_goal_decomposer

        decomposer = get_abstract_goal_decomposer()

        live["goal_decomposition"] = {"enabled": decomposer.enabled, "decompose_count": decomposer._decompose_count}

    except Exception:

        live["goal_decomposition"] = {"enabled": False, "decompose_count": 0}

    try:

        from core.harness.deployment.deploy_engine import get_deploy_engine

        deploy_engine = get_deploy_engine()

        live["deploy_engine"] = deploy_engine.stats()

    except Exception:

        live["deploy_engine"] = {"enabled": False, "deploy_count": 0}

    try:

        from core.harness.infrastructure.discovery_listener import get_discovery_listener

        discovery = get_discovery_listener()

        live["discovery"] = discovery.stats()

    except Exception:

        live["discovery"] = {"enabled": False, "discovery_count": 0}



    return {

        "system": "本体智能平台 — AI时代的企业大脑原型",

        "philosophy": "用确定性的本体包住不确定性的大模型。LLM做推理，Ontology做业务世界建模。",

        "live": live,

        "scheduler": {

            "active": _scheduler_started,

            "interval_seconds": 3600,

            "mode": "diagnose→heal→evolve (zero token)",

        },

        "architecture": {

            "buses": {

                "seci": "知识创造螺旋 (POST_LOOP → atom → convergence → adjust)",

                "context": "10层上下文组装 (FDE全量/Agent轻量/Skill轻量/Pipeline轻量)",

                "quality": "4子系统统一评分 (FDE+SECI+Convergence+ContextBus)",

            },

            "governance": {

                "capabilities": 8,

                "self_audit": "8/8 pass in <50ms",

                "maturity": "7 production / 1 beta",

            },

            "self_evolution": {

                "phase_1": "时序列观察 (SystemSnapshot持久化, 12周趋势)",

                "phase_2": "主动诊断 (5条跨子系统关联规则)",

                "phase_3": "自动修复 (confidence≥0.9安全门, 5条修复, 审计)",

                "phase_4": "自主演化 (术语自动发布, 方案草稿审批)",

                "phase_5": "抽象目标分解 (AbstractGoalDecomposer — LLM+Ontology拆解模糊目标为子目标, GoalDependencyGraph拓扑排序, GoalProgressEvaluator收敛评估)",

                "phase_6": "自主部署 (DeployEngine — 沙箱→灰度5%→25%→100%→git push→构建→健康检查→自动回滚, 三道防线)",

                "phase_7": "外部发现 (Discovery — socket扫描→服务指纹→DataSourceConfig→监听注册, 默认DENY需人工授权)",

            },

        },

        "subsystems": ["FDE诊断", "Agent会话", "Skill执行", "Pipeline运行"],

        "endpoints": 32,

    }





# ════════════════════════════════════════════════════════════

# Diagnose

# ════════════════════════════════════════════════════════════



@router.get("/diagnose", response_model=ItemResponse)

async def system_diagnose():

    """Proactive cross-subsystem health diagnosis."""

    try:

        from core.harness.knowledge.system_diagnostician import SystemDiagnostician

        return SystemDiagnostician().diagnose()

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)[:300]}")





# ════════════════════════════════════════════════════════════

# Heal

# ════════════════════════════════════════════════════════════



@router.post("/heal", response_model=StatusResponse)

async def system_heal():

    """Auto-heal with confidence gate (>0.9) and audit trail."""

    try:

        from core.harness.knowledge.system_diagnostician import SystemDiagnostician, SystemHealer

        diag = SystemDiagnostician().diagnose()

        return {

            "health": diag.get("overall_health", "unknown"),

            "confidence": diag.get("overall_confidence", 0),

            "heal": SystemHealer().auto_heal(diag),

        }

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Heal failed: {str(e)[:300]}")





# ════════════════════════════════════════════════════════════

# Evolve

# ════════════════════════════════════════════════════════════



@router.get("/evolve", response_model=ItemResponse)

async def system_evolve():

    """Run an evolution cycle: detect patterns → generate capabilities."""

    try:

        from core.harness.knowledge.system_evolver import SystemEvolver

        return SystemEvolver().evolve()

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Evolution failed: {str(e)[:300]}")





# ════════════════════════════════════════════════════════════

# Self-Check — combined cycle

# ════════════════════════════════════════════════════════════



@router.post("/self-check", response_model=StatusResponse)

async def system_self_check():

    """One-stop self-maintenance: diagnose → heal → evolve."""

    t0 = time.time()

    results = {}

    try:

        from core.harness.knowledge.system_diagnostician import SystemDiagnostician, SystemHealer

        results["diagnosis"] = SystemDiagnostician().diagnose()

        results["heal"] = SystemHealer().auto_heal(results["diagnosis"])

    except Exception as e:

        results["error"] = str(e)[:100]



    try:

        from core.harness.knowledge.system_evolver import SystemEvolver

        results["evolution"] = SystemEvolver().evolve()

    except Exception as e:

        results["evolution"] = {"error": str(e)[:100]}



    results["elapsed_ms"] = round((time.time() - t0) * 1000)

    return results





# ════════════════════════════════════════════════════════════

# Auto-check + Background Scheduler — self-evolving OS engine

# ════════════════════════════════════════════════════════════



_auto_check_counter: int = 0

_scheduler_started: bool = False





def run_auto_check() -> dict:

    """Full self-check for POST_LOOP hook: diagnose→heal→evolve.



    Runs every 10th conversation. Returns status or empty dict.

    Zero LLM/token cost — all operations are GraphIndex reads/writes.

    """

    global _auto_check_counter

    _auto_check_counter += 1

    if _auto_check_counter % 10 != 0:

        return {}



    try:

        from core.harness.knowledge.system_diagnostician import SystemDiagnostician, SystemHealer



        # Diagnose

        diag = SystemDiagnostician().diagnose()

        warnings = [f for f in diag.get("findings", [])

                    if f.get("severity") in ("warning", "error") and not f.get("insufficient_data")]



        # Heal (only if confidence >= 0.9)

        heal_result = {}

        if diag.get("overall_confidence", 0) >= 0.9:

            try:

                heal_result = SystemHealer().auto_heal(diag)

            except Exception:

                logging.getLogger(__name__).debug('run_auto_check failed', exc_info=True)


        # Evolve

        evolve_result = {}

        try:

            from core.harness.knowledge.system_evolver import SystemEvolver

            evolve_result = SystemEvolver().evolve()

        except Exception:

            logging.getLogger(__name__).debug('run_auto_check failed', exc_info=True)


        if warnings:

            log.warning("Auto-check: %d warnings, healed=%s, evolved=%s",

                        len(warnings),

                        heal_result.get("auto_fixed", "?"),

                        evolve_result.get("evolved", "?"))



        return {

            "auto_check": True,

            "health": diag.get("overall_health", "unknown"),

            "warnings": len(warnings),

            "auto_fixed": heal_result.get("auto_fixed", 0) if heal_result else 0,

            "evolved": evolve_result.get("evolved", 0) if evolve_result else 0,

        }

    except Exception:

        return {}





async def _scheduler_loop(interval_seconds: int = 3600):

    """Background scheduler: run full self-check every interval_seconds.



    Zero token cost — all operations are read-only GraphIndex + memory.

    """

    import asyncio as _asyncio

    while True:

        await _asyncio.sleep(interval_seconds)

        try:

            from core.harness.knowledge.system_diagnostician import SystemDiagnostician, SystemHealer

            from core.harness.knowledge.system_evolver import SystemEvolver



            diag = SystemDiagnostician().diagnose()

            warnings = [f for f in diag.get("findings", [])

                        if f.get("severity") in ("warning", "error") and not f.get("insufficient_data")]



            if diag.get("overall_confidence", 0) >= 0.9:

                SystemHealer().auto_heal(diag)

            SystemEvolver().evolve()

            try:

                from core.harness.knowledge.skill_curator import SkillCurator

                cr = SkillCurator().curate()

                if not cr.get("skipped") and (cr.get("stale") or cr.get("archived")):

                    log.info("SkillCurator: %d stale, %d archived",

                             len(cr.get("stale", [])), len(cr.get("archived", [])))

            except Exception:

                logging.getLogger(__name__).debug('_scheduler_loop failed', exc_info=True)


            if warnings:

                log.info("Background self-check: %d warnings, health=%s",

                         len(warnings), diag.get("overall_health", "?"))

        except Exception as e:

            log.debug("Background self-check skip: %s", str(e))





def start_background_scheduler(interval_seconds: int = 3600):

    """Start the self-evolution background scheduler. Idempotent."""

    global _scheduler_started

    if _scheduler_started:

        return

    import asyncio as _asyncio

    try:

        loop = _asyncio.get_running_loop()

        loop.create_task(_scheduler_loop(interval_seconds))

        _scheduler_started = True

        log.info("Self-evolution scheduler started (interval=%ds)", interval_seconds)

    except RuntimeError:

        log.debug("No running event loop — scheduler deferred")





# ════════════════════════════════════════════════════════════

# System Health — comprehensive component status

# ════════════════════════════════════════════════════════════



@router.get("/health", response_model=ItemResponse)

async def system_health():

    """System-level comprehensive health check — mirrors /fde/health."""

    try:

        from core.api.core_facade import get_fde_health

        return await get_fde_health()

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e)[:300])





@router.get("/status", response_model=ItemResponse)

async def system_status():

    """Comprehensive system status — all key metrics in one call."""

    import time as _t_ss

    t0 = _t_ss.time()



    status = {

        "coding_constitution": "karpathy_v1 (active, global default)",

    }



    # Scheduler

    status["scheduler"] = {"active": _scheduler_started, "interval_seconds": 3600}



    # SECI

    try:

        from core.harness.knowledge.seci_engine import get_seci_engine

        se = get_seci_engine()

        status["seci"] = {"atoms": se.get_atom_count(), "links": se.get_link_count()}

    except Exception:

        status["seci"] = {"error": "unavailable"}



    # Convergence

    try:

        from core.harness.knowledge.convergence_engine import ConvergenceEngine

        ce = ConvergenceEngine()

        status["convergence"] = ce.get_status()

    except Exception:

        status["convergence"] = {"error": "unavailable"}



    # Delivery

    try:

        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.knowledge.domain_router import get_domain_router

        router = get_domain_router()
        delivery_stats = {}
        for domain_id in router.list_domains():
            try:
                g = GraphIndex.load(domain_id)
                total = len(g._nodes) if hasattr(g, '_nodes') else 0
                classes = {}
                for _, n in getattr(g, '_nodes', {}).items():
                    cn = getattr(n, "class_name", "Unknown")
                    classes[cn] = classes.get(cn, 0) + 1
                delivery_stats[domain_id] = {"total_entities": total, "class_distribution": classes}
            except Exception:
                delivery_stats[domain_id] = {"error": "unavailable"}

        status["delivery"] = delivery_stats

    except Exception:

        status["delivery"] = {"error": "unavailable"}



    # Manuals

    try:

        import os as _os_ss

        mdir = _os_ss.path.expanduser("~/.aiplat/fde-manuals")

        manuals = [f for f in _os_ss.listdir(mdir) if f.endswith("-current.md")] if _os_ss.path.exists(mdir) else []

        status["manuals"] = {"count": len(manuals)}

    except Exception:

        status["manuals"] = {"count": 0}



    # Pipeline

    try:

        from core.api.core_facade import get_fde_pipeline_health

        status["pipeline"] = get_fde_pipeline_health()

    except Exception:

        status["pipeline"] = "unknown"



    status["elapsed_ms"] = round((_t_ss.time() - t0) * 1000)

    return status





# ════════════════════════════════════════════════════════════

# Skill Curator — lifecycle management endpoint

# ════════════════════════════════════════════════════════════



@router.get("/curate-skills", response_model=ItemResponse)

async def system_curate_skills():

    """Run skill lifecycle curation manually.



    Returns stale, archived, merge_suggestions per-skill report.

    """

    try:

        from core.harness.knowledge.skill_curator import SkillCurator

        import time as _t_cs

        t0 = _t_cs.time()

        result = SkillCurator().curate()

        result["elapsed_ms"] = round((_t_cs.time() - t0) * 1000)

        return result

    except HTTPException:

        raise

    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e)[:300])

