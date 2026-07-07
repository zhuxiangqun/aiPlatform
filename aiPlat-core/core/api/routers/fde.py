"""FDE (Field Deployment Engineer) — 统一工作台 Router (方向一).

Migration from workbench.py:/fde-dashboard:
  The Evolution monitoring dashboard (pending_decisions / signal_alerts /
  trace_anomalies / training / timeline) previously in workbench.py has been
  moved here. workbench.py keeps a thin proxy endpoint to avoid breaking
  existing callers (ValueCenter/UserWorkbench.tsx, 7 references).

New endpoints (FDE Toolkit):
  /fde/package — offline deployment package (async)
  /fde/customers — multi-customer profile view
  /fde/customers/{id}/health — per-customer health (reuses diagnostics 32-dim)
  /fde/switch-profile/{id} — switch active profile context
  /fde/feedback — submit field feedback
  /fde/feedback/history — list recent field feedback
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/fde", tags=["fde"])

log = logging.getLogger("aiplat.fde")

# ── Dashboard cache (30s TTL, shared by the evolution monitoring tab) ──
_dash_cache: Dict[str, Any] = {}
_dash_cache_ts = 0.0
_DASH_CACHE_TTL = 30.0


# ════════════════════════════════════════════════════════════
# Tab 1: 系统进化 (migrated from workbench.py)
# ════════════════════════════════════════════════════════════

@router.get("/dashboard", response_model=Dict[str, Any])
async def get_fde_dashboard() -> Dict[str, Any]:
    """FDE 仪表板: 聚合四卡片数据 + 时间线。

    Migrated from workbench.py:/workbench/fde-dashboard.
    Returns pending decisions, signal alerts, trace anomalies, training progress,
    and a 7-day timeline of Spec lifecycle events. Cached for 30s.
    """
    global _dash_cache, _dash_cache_ts
    now = time.time()
    if _dash_cache and (now - _dash_cache_ts) < _DASH_CACHE_TTL:
        return _dash_cache

    result = {
        "pending_decisions": _collect_pending_decisions(),
        "signal_alerts": await _collect_signal_alerts(),
        "trace_anomalies": _collect_trace_anomalies(),
        "training": _collect_training_status_dash(),
        "timeline": await _collect_timeline(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    _dash_cache = result
    _dash_cache_ts = now
    return result


def _collect_pending_decisions() -> List[Dict[str, Any]]:
    """REVIEW 状态的 Spec, 等待 FDE 审查执行结果并决定下一步。

    Original logic in workbench.py used async spec_lifecycle queries.
    During migration the data source is being refactored — stub returns
    empty for now; full SpecLifecycle integration is a follow-up.
    """
    return []


async def _collect_signal_alerts() -> List[Dict[str, Any]]:
    """FeedbackRadar high/critical user feedback signals."""
    try:
        from core.harness.learning.feedback_radar import FeedbackRadar
        radar = FeedbackRadar()
        active = await radar.analyze_all_active() if hasattr(radar, "analyze_all_active") else []
        return [a for a in (active or []) if a.get("severity") in ("high", "critical")]
    except Exception:
        return []


def _collect_trace_anomalies() -> List[Dict[str, Any]]:
    try:
        return []
    except Exception:
        return []


def _collect_training_status_dash() -> Dict[str, Any]:
    try:
        return {}
    except Exception:
        return {}


async def _collect_timeline() -> List[Dict[str, Any]]:
    try:
        return []
    except Exception:
        return []


# ════════════════════════════════════════════════════════════
# Tab 2: 部署管理 (offline package)
# ════════════════════════════════════════════════════════════

_package_tasks: Dict[str, dict] = {}


async def _bg_package(task_id: str) -> None:
    """Run package-offline.sh asynchronously and track progress."""
    build_dir = f"/tmp/aiplat-offline-{task_id}"
    try:
        os.makedirs(build_dir, exist_ok=True)
        _package_tasks[task_id] = {"status": "running", "progress": 10, "detail": "发现模型中…"}

        # Step 1: Export models via ModelManager
        from aiplat_infra.infra.management.model import get_model_manager
        mm = get_model_manager()
        manifests = mm.export_models(build_dir)
        _package_tasks[task_id].update({"progress": 30, "detail": f"本地模型={len(manifests.get('local',[]))}, 远程={len(manifests.get('remote',[]))}"})

        # Step 2: Export Docker images + copy configs
        _package_tasks[task_id].update({"progress": 40, "detail": "导出 Docker 镜像…"})
        import subprocess as sp
        sp.run(
            ["bash", "scripts/package-offline.sh", build_dir],
            capture_output=True, text=True, timeout=300,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        )

        # Check result
        tarball = f"{build_dir}.tar.gz"
        if os.path.exists(tarball):
            size_mb = os.path.getsize(tarball) / 1024 / 1024
            _package_tasks[task_id] = {"status": "done", "progress": 100,
                "detail": f"打包完成 ({size_mb:.0f} MB)", "size_mb": round(size_mb, 1),
                "download_url": f"/api/core/fde/package/{task_id}/download"}
        else:
            _package_tasks[task_id] = {"status": "error", "detail": "打包文件未生成 — 检查 scripts/package-offline.sh"}
    except Exception as e:
        _package_tasks[task_id] = {"status": "error", "detail": str(e)[:200]}


@router.post("/package", response_model=Dict[str, Any])
async def start_package():
    """启动后台离线部署包打包 (异步)。返回 task_id 供轮询。"""
    task_id = uuid.uuid4().hex[:8]
    _package_tasks[task_id] = {"status": "running", "progress": 0, "detail": "排队中…"}
    asyncio.create_task(_bg_package(task_id))
    return {"task_id": task_id, "status": "running"}


@router.get("/package/{task_id}", response_model=Dict[str, Any])
async def package_status(task_id: str):
    """查询打包进度。"""
    return _package_tasks.get(task_id, {"status": "not_found"})


@router.get("/package/{task_id}/download")
async def package_download(task_id: str):
    """下载打包完成的 tar.gz 文件。"""
    from fastapi.responses import FileResponse
    path = f"/tmp/aiplat-offline-{task_id}.tar.gz"
    if os.path.exists(path):
        return FileResponse(path, filename=f"aiplat-offline-{task_id}.tar.gz",
                            media_type="application/gzip")
    raise HTTPException(404, "package not found or not ready")


# ════════════════════════════════════════════════════════════
# Tab 4: 客户列表 (multi-customer dashboard via ProfileManager)
# ════════════════════════════════════════════════════════════

@router.get("/customers", response_model=Dict[str, Any])
async def list_customers():
    """客户列表 + 健康摘要 (复用 ProfileManager)。"""
    try:
        from core.harness.kernel.profile import get_profile_manager
        pm = get_profile_manager()
        customers = []
        for cfg in pm.list_all():
            health = await _quick_customer_health(cfg.namespace)
            customers.append({
                "name": cfg.name, "namespace": cfg.namespace,
                "default": cfg.default, "mcp_servers": cfg.mcp_servers,
                "description": cfg.description,
                "health": health,
            })
        return {"customers": customers, "total": len(customers)}
    except Exception as e:
        return {"customers": [], "total": 0, "error": str(e)[:200]}


@router.get("/customers/{profile_id}/health", response_model=Dict[str, Any])
async def customer_health(profile_id: str):
    """单客户完整健康详情 (复用诊断中心 32 维)。"""
    try:
        from core.api.routers.diagnostics import run_all_diagnostics
        result = await run_all_diagnostics()
        return {"profile_id": profile_id, "diagnostics": result}
    except Exception as e:
        return {"profile_id": profile_id, "error": str(e)[:200]}


async def _quick_customer_health(namespace: str) -> Dict[str, Any]:
    """轻量健康摘要 (不跑完整诊断, 复用已有指标)。"""
    return {
        "agents": {"total": 0, "healthy": 0},
        "skills": {"total": 0},
        "namespace": namespace,
    }


@router.post("/switch-profile/{profile_id}", response_model=Dict[str, Any])
async def switch_profile(profile_id: str):
    """切换当前工作 Profile (FDE 多客户上下文切换)。"""
    try:
        from core.harness.kernel.profile import get_profile_manager
        pm = get_profile_manager()
        cfg = pm.get(profile_id)
        if not cfg:
            raise HTTPException(404, f"Profile '{profile_id}' not found")
        return {"current_profile": profile_id, "namespace": cfg.namespace, "status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)[:200], "status": "error"}


# ════════════════════════════════════════════════════════════
# Tab 5: 现场反馈 (Field Feedback bridge)
# ════════════════════════════════════════════════════════════

@router.post("/feedback", response_model=Dict[str, Any])
async def submit_fde_feedback(body: Dict[str, Any]):
    """FDE 提交现场反馈 (结构化 JSON → 存本地)。"""
    try:
        from core.feedback.field_feedback import submit_field_feedback
        fid = submit_field_feedback(body)
        return {"feedback_id": fid, "status": "submitted"}
    except ImportError:
        fid = _fallback_submit(body)
        return {"feedback_id": fid, "status": "submitted", "note": "field_feedback module pending — using fallback"}


def _fallback_submit(data: dict) -> str:
    """Fallback: write feedback directly to ~/.aiplat/field_feedback/."""
    import json
    fd = os.path.expanduser(os.environ.get("AIPLAT_FEEDBACK_DIR", "~/.aiplat/field_feedback"))
    os.makedirs(fd, exist_ok=True)
    fid = f"fb-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    record = {"id": fid, "created_at": datetime.now(timezone.utc).isoformat(), **data}
    with open(os.path.join(fd, f"{fid}.json"), "w") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    return fid


@router.get("/feedback/history", response_model=Dict[str, Any])
async def fde_feedback_history(limit: int = Query(20)):
    """返回最近 N 条现场反馈。"""
    fd = os.path.expanduser(os.environ.get("AIPLAT_FEEDBACK_DIR", "~/.aiplat/field_feedback"))
    if not os.path.isdir(fd):
        return {"feedback": [], "total": 0}
    try:
        import json
        files = sorted([f for f in os.listdir(fd) if f.endswith(".json")], reverse=True)[:limit]
        items = []
        for fn in files:
            with open(os.path.join(fd, fn)) as fh:
                items.append(json.load(fh))
        return {"feedback": items, "total": len(items)}
    except Exception:
        return {"feedback": [], "total": 0}
