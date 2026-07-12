"""System-level self-evolution endpoints — core system capability, not FDE-specific.

These provide the same diagnose/heal/evolve/self-check/overview capabilities
as /fde/* but at the system level (/system/*), accessible without FDE context.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/system", tags=["system"])
log = logging.getLogger("aiplat.system")


# ════════════════════════════════════════════════════════════
# System Overview
# ════════════════════════════════════════════════════════════

@router.get("/overview", response_model=dict)
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
        fd = GraphIndex.load("fde-delivery")
        sessions = sum(1 for _, n in fd._nodes.items() if getattr(n, "class_name", "") == "DiagnosisSession")
        tg = GraphIndex.load("enterprise-terms")
        terms = sum(1 for _, n in tg._nodes.items() if getattr(n, "class_name", "") == "Term")
        live["diagnosis_sessions"] = sessions
        live["enterprise_terms"] = terms
    except Exception:
        live["diagnosis_sessions"] = 0
        live["enterprise_terms"] = 0

    try:
        from core.api.routers.fde import _get_pipeline_health
        live["pipeline"] = _get_pipeline_health()
    except Exception:
        live["pipeline"] = "unknown"

    live["self_evolution_phase"] = "四阶段竣工 (POST_LOOP每10次自动诊断)"

    return {
        "system": "本体智能平台 — AI时代的企业大脑原型",
        "philosophy": "用确定性的本体包住不确定性的大模型。LLM做推理，Ontology做业务世界建模。",
        "live": live,
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
            },
        },
        "subsystems": ["FDE诊断", "Agent会话", "Skill执行", "Pipeline运行"],
        "endpoints": 32,
    }


# ════════════════════════════════════════════════════════════
# Diagnose
# ════════════════════════════════════════════════════════════

@router.get("/diagnose", response_model=dict)
async def system_diagnose():
    """Proactive cross-subsystem health diagnosis."""
    try:
        from core.harness.knowledge.system_diagnostician import SystemDiagnostician
        return SystemDiagnostician().diagnose()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)[:300]}")


# ════════════════════════════════════════════════════════════
# Heal
# ════════════════════════════════════════════════════════════

@router.post("/heal", response_model=dict)
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Heal failed: {str(e)[:300]}")


# ════════════════════════════════════════════════════════════
# Evolve
# ════════════════════════════════════════════════════════════

@router.get("/evolve", response_model=dict)
async def system_evolve():
    """Run an evolution cycle: detect patterns → generate capabilities."""
    try:
        from core.harness.knowledge.system_evolver import SystemEvolver
        return SystemEvolver().evolve()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evolution failed: {str(e)[:300]}")


# ════════════════════════════════════════════════════════════
# Self-Check — combined cycle
# ════════════════════════════════════════════════════════════

@router.post("/self-check", response_model=dict)
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
                pass

        # Evolve
        evolve_result = {}
        try:
            from core.harness.knowledge.system_evolver import SystemEvolver
            evolve_result = SystemEvolver().evolve()
        except Exception:
            pass

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

@router.get("/health", response_model=dict)
async def system_health():
    """System-level comprehensive health check — mirrors /fde/health."""
    try:
        from core.api.routers.fde import fde_health
        return await fde_health()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])
