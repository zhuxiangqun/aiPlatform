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
    """System-level self-description — not gated behind FDE."""
    return {
        "system": "本体智能平台 — AI时代的企业大脑原型",
        "philosophy": "用确定性的本体包住不确定性的大模型。LLM做推理，Ontology做业务世界建模。",
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
# Lightweight auto-check — for periodic hooks
# ════════════════════════════════════════════════════════════

_auto_check_counter: int = 0

def run_auto_check() -> dict:
    """Lightweight auto-check for POST_LOOP hook integration.

    Runs every 10th call. Returns quick status or empty dict.
    """
    global _auto_check_counter
    _auto_check_counter += 1
    if _auto_check_counter % 10 != 0:
        return {}

    try:
        from core.harness.knowledge.system_diagnostician import SystemDiagnostician
        diag = SystemDiagnostician().diagnose()
        warnings = [f for f in diag.get("findings", []) if f.get("severity") in ("warning", "error") and not f.get("insufficient_data")]
        if warnings:
            log.warning("Auto-check: %d warnings detected", len(warnings))
        return {"auto_check": True, "health": diag.get("overall_health", "unknown"), "warnings": len(warnings)}
    except Exception:
        return {}
