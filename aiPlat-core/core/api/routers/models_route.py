"""
Models route — v3.0 LLM routing statistics + scoring profile endpoints.
Exposes quality scores, latency, fallback, cost metrics, and scoring weights
configuration for all purposes.
"""
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Body
import time as _time

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/profile", response_model=Dict[str, Any])
async def get_scoring_profile():
    """读取当前生效的 purpose_profiles + scoring_weights（合并系统+工作区配置）。"""
    try:
        from core.harness.utils.model_injection import _load_llm_profile
        profile = _load_llm_profile()
        return {
            "purpose_profiles": profile.get("purpose_profiles", {}),
            "default_scoring_weights": profile.get("default_scoring_weights", {}),
            "fallback": profile.get("fallback", {}),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


@router.put("/profile", response_model=Dict[str, Any])
async def update_scoring_profile(body: Dict[str, Any] = Body(...)):
    """更新工作区 config/infra/llm_profile.yaml 中的评分权重配置。"""
    try:
        import yaml
        from pathlib import Path

        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        ws_path = project_root / "config" / "infra" / "llm_profile.yaml"
        ws_path.parent.mkdir(parents=True, exist_ok=True)

        current = {}
        if ws_path.is_file():
            with open(ws_path) as f:
                current = yaml.safe_load(f) or {}

        if "purpose_profiles" in body:
            current["purpose_profiles"] = body["purpose_profiles"]
        if "default_scoring_weights" in body:
            current["default_scoring_weights"] = body["default_scoring_weights"]
        if "fallback" in body:
            current["fallback"] = body["fallback"]

        with open(ws_path, "w") as f:
            yaml.safe_dump(current, f, allow_unicode=True, default_flow_style=False)

        return {"status": "ok", "written": str(ws_path)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


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
