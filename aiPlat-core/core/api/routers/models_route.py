import logging
from typing import Dict, Any
"""
Models route — v3.0 LLM routing statistics endpoint.
Exposes quality scores, latency, fallback, cost metrics for all purposes.
"""
from fastapi import APIRouter
import time as _time

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/v3-stats", response_model=Dict[str, Any])
async def get_v3_route_stats():
    """v3.0 LLM routing monitoring dashboard data (all purposes)."""
    snapshot = {"generated_at": _time.time()}

    try:
        from infra.management.model.quality_validator import get_quality_tracker
        qt = get_quality_tracker()
        quality = {}
        for model, purposes in qt.to_dict().items():
            for purpose, score in purposes.items():
                key = f"{model}|{purpose}"
                quality[key] = round(score, 3)
        snapshot["quality"] = quality
    except Exception:
        snapshot["quality"] = {}

    try:
        from infra.management.model.latency_tracker import get_latency_tracker
        lt = get_latency_tracker()
        latency = {}
        known_models = ["qwen2.5-coder:7b", "qwen2.5-coder:14b", "qwen2.5-coder:32b",
                         "gemma4:12b", "minicpm-v:8b", "deepseek-v4-pro"]
        for model in known_models:
            try:
                latency[model] = {
                    "p95_s": round(lt.p95_latency_seconds(model), 2),
                    "congestion": round(lt.congestion_penalty(model), 0),
                }
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        snapshot["latency"] = latency
    except Exception:
        snapshot["latency"] = {}

    try:
        from core.harness.utils.model_injection import get_route_metrics
        rm = get_route_metrics()
        total = max(rm["total_calls"], 1)
        snapshot["routes"] = {
            "total_calls": rm["total_calls"],
            "fallback_rate": round(rm["fallback_count"] / total, 3),
            "avg_attempts": round(rm["total_attempts"] / total, 2),
            "local_calls": rm["local_calls"],
            "external_calls": rm["external_calls"],
            "external_ratio": round(rm["external_calls"] / total, 3),
            "complexity": dict(rm["complexity_dist"]),
            "recent_logs": rm["recent_logs"][-20:],
        }
    except Exception:
        snapshot["routes"] = {"total_calls": 0, "recent_logs": []}

    return snapshot
