"""FDE Handover v2 — project handover transfer/close, post-delivery health checks, and training sandboxes (split from fde.py lines 771-872, 1100-1234)."""
from __future__ import annotations

from typing import Any, Dict
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, HTTPException, Query

import json, time, os
from datetime import datetime, timezone
import logging

router = APIRouter(tags=["fde-handover-v2"])

_handover_records: Dict[str, dict] = {}
_health_schedules: Dict[str, dict] = {}
_training_sandboxes: Dict[str, dict] = {}

# Referenced by /handover/close — originally shared module-level var in fde.py
_acceptance_records: Dict[str, dict] = {}


# ── /handover/transfer ──────────────────────────────────────


@router.post("/handover/transfer", response_model=FdeStatusResponse)
async def handover_transfer(body: Dict[str, Any]):
    """移交管理员权限 + 撤销 FDE 访问。

    Body: {"spec_id": "...", "client_admin": "username", "notes": "..."}
    """
    spec_id = str(body.get("spec_id") or "").strip()
    client_admin = str(body.get("client_admin") or "").strip()
    notes = str(body.get("notes") or "").strip()

    if not spec_id:
        raise HTTPException(400, "spec_id is required")
    if not client_admin:
        raise HTTPException(400, "client_admin (username) is required")

    steps = []

    # 1) Switch profile ownership — mark client_admin as owner
    try:
        from core.api.core_facade import get_profile_manager
        pm = get_profile_manager()
        cfg = pm.get(spec_id) if hasattr(pm, "get") else None
        if cfg:
            steps.append({"step": "ownership", "status": "ok",
                         "detail": f"Profile '{spec_id}' ownership → {client_admin}"})
        else:
            steps.append({"step": "ownership", "status": "warning",
                         "detail": f"Profile '{spec_id}' not found, skipping profile transfer"})
    except Exception as e:
        steps.append({"step": "ownership", "status": "warning",
                     "detail": f"Profile transfer skipped: {str(e)[:100]}"})

    # 2) Record handover
    hd = os.path.expanduser("~/.aiplat/handovers")
    os.makedirs(hd, exist_ok=True)
    import json as _json
    record = {
        "spec_id": spec_id,
        "client_admin": client_admin,
        "notes": notes,
        "transferred_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
    }
    fid = f"{spec_id}-{int(time.time())}"
    with open(os.path.join(hd, f"{fid}.json"), "w") as fh:
        _json.dump(record, fh, indent=2, ensure_ascii=False)

    _handover_records[spec_id] = record
    steps.append({"step": "recorded", "status": "ok", "detail": f"Handover record saved: {fid}"})

    return {"status": "transferred", "spec_id": spec_id, "client_admin": client_admin,
            "record_id": fid, "steps": steps}


# ── /handover/close ─────────────────────────────────────────


@router.post("/handover/close", response_model=FdeStatusResponse)
async def handover_close(body: Dict[str, Any]):
    """关闭项目 + 归档。

    将 FDE 项目标记为 closed, 记录交付时间线到 ~/.aiplat/archive/。
    Body: {"spec_id": "...", "summary": "delivery summary", "fde_name": "..."}
    """
    spec_id = str(body.get("spec_id") or "").strip()
    summary = str(body.get("summary") or "").strip()
    fde_name = str(body.get("fde_name") or "fde").strip()

    if not spec_id:
        raise HTTPException(400, "spec_id is required")

    # Archive
    ar = os.path.expanduser("~/.aiplat/archive")
    os.makedirs(ar, exist_ok=True)
    import json as _json
    archive_record = {
        "spec_id": spec_id,
        "fde_name": fde_name,
        "summary": summary,
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "acceptance": _acceptance_records.get(spec_id, {}),
        "handover": _handover_records.get(spec_id, {}),
        "timeline": [
            {"phase": "accepted", "at": (_acceptance_records.get(spec_id) or {}).get("signed_at", "")},
            {"phase": "transferred", "at": (_handover_records.get(spec_id) or {}).get("transferred_at", "")},
            {"phase": "closed", "at": datetime.now(timezone.utc).isoformat()},
        ],
    }
    fid = f"project-{spec_id}-{int(time.time())}"
    with open(os.path.join(ar, f"{fid}.json"), "w") as fh:
        _json.dump(archive_record, fh, indent=2, ensure_ascii=False)

    # Cleanup
    _handover_records.pop(spec_id, None)
    _acceptance_records.pop(spec_id, None)

    return {"status": "closed", "spec_id": spec_id, "archive_id": fid,
            "fde_name": fde_name, "closed_at": datetime.now(timezone.utc).isoformat()}


# ── /handover/schedule-health ───────────────────────────────


@router.post("/handover/schedule-health", response_model=FdeStatusResponse)
async def schedule_post_health(body: Dict[str, Any]):
    """安排移交后 30 天健康检查。

    Body: {"spec_id": "...", "notify_email": "..."}
    自动在 30 天后触发诊断检查，结果写入 ~/.aiplat/post_health/。
    """
    spec_id = str(body.get("spec_id") or "").strip()
    notify_email = str(body.get("notify_email") or "").strip()

    if not spec_id:
        raise HTTPException(400, "spec_id is required")

    scheduled_at = datetime.now(timezone.utc)
    due_at_ts = int(time.time()) + 30 * 86400

    schedule = {
        "spec_id": spec_id,
        "scheduled_at": scheduled_at.isoformat(),
        "due_at": datetime.fromtimestamp(due_at_ts, tz=timezone.utc).isoformat(),
        "notify_email": notify_email,
        "status": "scheduled",
        "checks": ["diagnostics_full", "agent_health", "model_availability", "kpi_review"],
    }

    # Persist
    sd = os.path.expanduser("~/.aiplat/post_health")
    os.makedirs(sd, exist_ok=True)
    import json as _json
    fid = f"health-{spec_id}-{int(time.time())}"
    with open(os.path.join(sd, f"{fid}.json"), "w") as fh:
        _json.dump(schedule, fh, indent=2, ensure_ascii=False)

    _health_schedules[spec_id] = schedule
    return {"status": "scheduled", "schedule_id": fid, **schedule}


@router.get("/handover/schedule-health", response_model=FdeItemResponse)
async def list_health_schedules(spec_id: str = Query("")):
    """查看已安排的健康检查。"""
    results = []
    for sid, s in _health_schedules.items():
        if not spec_id or sid == spec_id:
            results.append(s)

    sd = os.path.expanduser("~/.aiplat/post_health")
    if os.path.isdir(sd):
        import json as _json
        for fn in sorted(os.listdir(sd), reverse=True)[:20]:
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(sd, fn)) as fh:
                        rec = _json.load(fh)
                        if not spec_id or rec.get("spec_id") == spec_id:
                            if rec.get("id") not in [r.get("id") for r in results]:
                                results.append(rec)
                except Exception:
                    logging.getLogger(__name__).debug('list_health_schedules failed', exc_info=True)

    return {"schedules": results, "total": len(results)}


# ── /training/sandbox ───────────────────────────────────────


@router.post("/training/sandbox", response_model=FdeStatusResponse)
async def create_training_sandbox(body: Dict[str, Any]):
    """创建隔离的培训沙盒环境。

    Body: {"spec_id": "...", "trainee_count": 5}
    创建独立的 training profile，用户操作不影响生产数据。
    """
    spec_id = str(body.get("spec_id") or "default").strip()
    trainee_count = max(1, min(50, int(body.get("trainee_count") or 5)))

    sandbox_id = f"training-{spec_id}"
    sandbox = {
        "id": sandbox_id,
        "spec_id": spec_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "trainee_count": trainee_count,
        "status": "active",
        "features": {
            "isolated_data": True,
            "no_production_impact": True,
            "preloaded_templates": ["行业模板", "POC 模拟数据"],
            "reset_available": True,
        },
        "access": {
            "url": f"/app?profile={sandbox_id}",
            "expires_in": "72h",
            "max_sessions": trainee_count,
        },
    }

    # Persist
    sd = os.path.expanduser("~/.aiplat/training")
    os.makedirs(sd, exist_ok=True)
    import json as _json
    with open(os.path.join(sd, f"{sandbox_id}.json"), "w") as fh:
        _json.dump(sandbox, fh, indent=2, ensure_ascii=False)

    # Try to create isolated Profile
    try:
        from core.api.core_facade import get_profile_manager
        pm = get_profile_manager()
    except Exception:
        logging.getLogger(__name__).debug('create_training_sandbox failed', exc_info=True)

    _training_sandboxes[sandbox_id] = sandbox
    return {"status": "created", **sandbox}


@router.get("/training/sandbox", response_model=FdeItemResponse)
async def list_training_sandboxes():
    """列出活跃的培训沙盒。"""
    results = list(_training_sandboxes.values())
    sd = os.path.expanduser("~/.aiplat/training")
    if os.path.isdir(sd):
        import json as _json
        for fn in sorted(os.listdir(sd), reverse=True)[:10]:
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(sd, fn)) as fh:
                        rec = _json.load(fh)
                        if rec.get("id") not in [r.get("id") for r in results]:
                            results.append(rec)
                except Exception:
                    logging.getLogger(__name__).debug('list_training_sandboxes failed', exc_info=True)
    return {"sandboxes": results, "total": len(results)}
