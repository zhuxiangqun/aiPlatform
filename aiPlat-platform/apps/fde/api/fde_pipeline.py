"""FDE Pipeline — ContextBus pipeline health diagnostics (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException

import time
import os

router = APIRouter(tags=["fde-pipeline"])


@router.get("/pipeline-status", response_model=FdeItemResponse)
async def fde_pipeline_status():
    """Report ContextBus pipeline health: per-layer status, timing, data availability.

    Runs a lightweight test injection (no LLM call) and returns per-layer diagnostics.
    """
    import time as _t_ps
    t0 = _t_ps.time()

    try:
        from core.api.core_facade import assemble_field_assessment
        _, diag = assemble_field_assessment(
            {"industry": "pipeline-test", "company_name": "self-check", "pain_points": "test"},
            [],
        )
    except Exception as e:
        diag = {"_fatal": str(e)[:100]}

    elapsed_ms = round((_t_ps.time() - t0) * 1000)
    ok = sum(1 for v in diag.values() if v == "ok")
    total = sum(1 for k in diag if not k.startswith("_"))

    # Data availability summary
    data_status = {}
    try:
        from core.api.core_facade import wiki_search_pages, get_graph_health

        # Wiki/historical cases
        try:
            h = wiki_search_pages("诊断报告", collection_id="default", limit=1)
            data_status["historical_cases"] = f"{len(h)} available" if h else "empty"
        except Exception:
            data_status["historical_cases"] = "error"

        # Graph indices
        for domain in ["ai-knowledge", "fde-delivery", "enterprise-terms", "knowledge-atom"]:
            data_status[f"graph:{domain}"] = get_graph_health(domain).get("node_count", "error")

        # YAMLs
        import os as _os_ps
        for yaml_name in ["ai-solution.yaml", "enterprise-terms.yaml"]:
            path = _os_ps.path.expanduser(f"~/.aiplat/ontologies/{yaml_name}")
            data_status[f"yaml:{yaml_name}"] = "ok" if _os_ps.path.exists(path) else "missing"
    except Exception:
        data_status["_error"] = "Could not check data sources"

    return {
        "layers": {k: v for k, v in diag.items() if not k.startswith("_")},
        "layers_ok": ok,
        "layers_total": total,
        "health": "ok" if ok == total else "degraded" if ok > 0 else "error",
        "elapsed_ms": elapsed_ms,
        "data_availability": data_status,
    }
