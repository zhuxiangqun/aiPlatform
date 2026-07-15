"""FDE Acceptance — delivery acceptance checklist generation and signoff (split from fde.py lines 650-768)."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Query

import json, time, os
from datetime import datetime, timezone

router = APIRouter(tags=["fde-acceptance"])

_acceptance_records: Dict[str, dict] = {}


@router.get("/acceptance/checklist", response_model=Dict[str, Any])
async def acceptance_checklist(spec_id: str = Query("")):
    """生成交付验收 Checklist。

    聚合 KPI 达标情况 + 用户反馈统计 + SLA 指标，
    返回结构化的验收清单供 FDE 逐项确认。
    """
    checklist = []

    # 1) KPI check — from ValueDashboard KPI data
    try:
        from core.harness.learning.kpi_tracker import get_kpi_tracker
        tracker = get_kpi_tracker()
        kpis = tracker.get_all(spec_id=spec_id) if spec_id else tracker.get_all()
        kpi_met = sum(1 for k in (kpis or []) if k.get("met", False))
        kpi_total = len(kpis) if kpis else 0
        checklist.append({
            "id": "kpi",
            "label": "KPI 达标检查",
            "status": "pass" if kpi_met >= kpi_total > 0 else ("pending" if kpi_total == 0 else "fail"),
            "detail": f"{kpi_met}/{kpi_total} KPI 达标" if kpi_total > 0 else "无 KPI 配置",
        })
    except Exception:
        checklist.append({"id": "kpi", "label": "KPI 达标检查", "status": "pending",
                         "detail": "KPI tracker 不可用"})

    # 2) NPS / user feedback
    try:
        fd = os.path.expanduser(os.environ.get("AIPLAT_FEEDBACK_DIR", "~/.aiplat/field_feedback"))
        if os.path.isdir(fd):
            import json as _json
            files = sorted([f for f in os.listdir(fd) if f.endswith(".json")], reverse=True)[:50]
            positive = 0
            total = len(files)
            for fn in files:
                with open(os.path.join(fd, fn)) as fh:
                    rec = _json.load(fh)
                    if rec.get("issue", {}).get("category") in ("usability", "integration"):
                        positive += 1
            checklist.append({
                "id": "feedback",
                "label": "用户反馈质量",
                "status": "pass" if total == 0 or positive / max(total, 1) >= 0.7 else "fail",
                "detail": f"正向反馈 {positive}/{total}" if total > 0 else "无反馈记录",
            })
        else:
            checklist.append({"id": "feedback", "label": "用户反馈质量", "status": "pending", "detail": "无反馈记录"})
    except Exception:
        checklist.append({"id": "feedback", "label": "用户反馈质量", "status": "pending", "detail": "反馈读取失败"})

    # 3) SLA — check diagnostics summary
    try:
        from core.api.routers.diagnostics import run_all_diagnostics
        diag = await run_all_diagnostics()
        error_count = diag.get("errors", 0) if isinstance(diag, dict) else 0
        checklist.append({
            "id": "sla",
            "label": "系统健康 (SLA)",
            "status": "pass" if error_count == 0 else "fail",
            "detail": f"诊断错误: {error_count}" if error_count else "所有检查通过",
        })
    except Exception:
        checklist.append({"id": "sla", "label": "系统健康 (SLA)", "status": "pending", "detail": "诊断不可用"})

    # 4) Training completion
    checklist.append({
        "id": "training",
        "label": "客户培训完成",
        "status": "pending",
        "detail": "需人工确认：客户团队已完成操作演练",
    })

    passed = sum(1 for c in checklist if c["status"] == "pass")
    ready = passed == len(checklist)

    return {
        "checklist": checklist,
        "passed": passed,
        "total": len(checklist),
        "ready_for_signoff": ready,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/acceptance/signoff", response_model=Dict[str, Any])
async def acceptance_signoff(body: Dict[str, Any]):
    """记录交付验收签收。

    Body: {"spec_id": "...", "signed_by": "fde_name", "notes": "..."}
    """
    spec_id = str(body.get("spec_id") or "unknown").strip()
    signed_by = str(body.get("signed_by") or "fde").strip()
    notes = str(body.get("notes") or "").strip()

    record = {
        "spec_id": spec_id,
        "signed_by": signed_by,
        "notes": notes,
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "checklist": (await acceptance_checklist(spec_id)) if spec_id != "unknown" else {},
    }

    # Persist to file
    ad = os.path.expanduser(os.environ.get("AIPLAT_ACCEPTANCE_DIR", "~/.aiplat/acceptance"))
    os.makedirs(ad, exist_ok=True)
    import json as _json
    fid = f"{spec_id}-{int(time.time())}"
    with open(os.path.join(ad, f"{fid}.json"), "w") as fh:
        _json.dump(record, fh, indent=2, ensure_ascii=False)

    _acceptance_records[spec_id] = record
    return {"status": "signed_off", "record_id": fid, **record}
