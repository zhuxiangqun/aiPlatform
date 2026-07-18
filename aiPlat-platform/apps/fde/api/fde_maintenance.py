"""FDE Maintenance — diagnose / heal / evolve / self-check (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict
from apps.fde.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["fde-maintenance"])


# ── Phase 2: System Diagnostician — proactive cross-subsystem analysis ──

@router.get("/diagnose", response_model=FdeItemResponse)
async def fde_diagnose():
    """Run proactive system diagnostics across all subsystems.

    Cross-references SECI, FDE, Skill, and Convergence data to identify
    systemic issues. Returns findings, correlations, and overall health.
    """
    try:
        from core.harness.knowledge.system_diagnostician import SystemDiagnostician
        sd = SystemDiagnostician()
        return sd.diagnose()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)[:300]}")


# ── Phase 3: System Healer — auto-fix with verification ──

@router.post("/heal", response_model=FdeStatusResponse)
async def fde_heal():
    """Auto-heal known diagnostic patterns with safety gate and verification.

    Requires diagnosis confidence >= 0.9 before applying fixes.
    All actions are audited via SystemSnapshot entities.
    """
    try:
        from core.harness.knowledge.system_diagnostician import SystemDiagnostician, SystemHealer
        sd = SystemDiagnostician()
        diagnosis = sd.diagnose()
        healer = SystemHealer()
        result = healer.auto_heal(diagnosis)
        return {
            "diagnosis_health": diagnosis.get("overall_health", "unknown"),
            "diagnosis_confidence": diagnosis.get("overall_confidence", 0),
            "heal_result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Heal failed: {str(e)[:300]}")


# ── Phase 4: System Evolver — pattern detection → capability generation ──

@router.get("/evolve", response_model=FdeItemResponse)
async def fde_evolve():
    """Run an evolution cycle: detect patterns → generate capabilities → publish/draft.

    Terms auto-publish when score >= 0.7.
    SolutionArchetypes are drafted for human approval.
    Skills are not auto-registered.
    """
    try:
        from core.harness.knowledge.system_evolver import SystemEvolver
        evolver = SystemEvolver()
        return evolver.evolve()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evolution failed: {str(e)[:300]}")


# ── Self-Check — one-stop system self-maintenance cycle ──

@router.post("/self-check", response_model=FdeStatusResponse)
async def fde_self_check():
    """Run a complete self-maintenance cycle: diagnose -> heal -> evolve.

    Single endpoint for autonomous system health management.
    """
    import time as _t_sc
    t0 = _t_sc.time()
    results = {}

    # Step 1: Diagnose
    try:
        from core.harness.knowledge.system_diagnostician import SystemDiagnostician
        sd = SystemDiagnostician()
        results["diagnosis"] = sd.diagnose()
    except Exception as e:
        results["diagnosis"] = {"error": str(e)[:100]}

    # Step 2: Heal (guarded by confidence)
    try:
        from core.harness.knowledge.system_diagnostician import SystemHealer
        healer = SystemHealer()
        results["heal"] = healer.auto_heal(results.get("diagnosis", {}))
    except Exception as e:
        results["heal"] = {"error": str(e)[:100]}

    # Step 3: Evolve
    try:
        from core.harness.knowledge.system_evolver import SystemEvolver
        results["evolution"] = SystemEvolver().evolve()
    except Exception as e:
        results["evolution"] = {"error": str(e)[:100]}

    results["elapsed_ms"] = round((_t_sc.time() - t0) * 1000)
    results["cycle"] = "diagnose->heal->evolve 完成"

    return results
