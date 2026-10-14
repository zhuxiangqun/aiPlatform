"""L1 monthly ops report (HYBRID_ENTERPRISE_DELIVERY §5 SKU L1).

Composes existing cost + KB health meters into a customer-facing monthly
运行报告. Soft-fails subsystems; never invents ¥ or health scores.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _daemon_snapshot() -> Dict[str, Any]:
    """Best-effort daemon_jobs inventory (L1 存活监控叙事)."""
    try:
        from governance.daemon_jobs import DaemonJobStore

        store = DaemonJobStore()
        jobs = []
        if hasattr(store, "list_jobs"):
            jobs = list(store.list_jobs() or [])
        elif hasattr(store, "list"):
            jobs = list(store.list() or [])
        running = 0
        for j in jobs:
            if not isinstance(j, dict):
                continue
            st = str(j.get("status") or j.get("state") or "").lower()
            if st in ("running", "active", "ok", "healthy"):
                running += 1
        return {
            "available": True,
            "total_jobs": len(jobs),
            "running_jobs": running,
            "note": "来自 DaemonJobStore；无则仅占位",
        }
    except Exception as e:
        logger.debug("monthly_ops daemon snapshot: %s", e, exc_info=True)
        return {"available": False, "reason": str(e)}


def build_monthly_ops_report(
    *,
    tenant_id: str = "default",
    window_hours: int = 720,
    project_id: str = "",
    collection_id: str = "default",
) -> Dict[str, Any]:
    from delivery.cost_report import build_delivery_cost_report
    from delivery.kb_health import build_kb_health_report

    cost = build_delivery_cost_report(
        tenant_id=tenant_id,
        window_hours=window_hours,
        project_id=project_id,
    )
    kb = build_kb_health_report(
        tenant_id=tenant_id,
        collection_id=collection_id,
        window_hours=min(int(window_hours), 168),
        project_id=project_id,
    )
    daemon = _daemon_snapshot()
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id or "default",
        "project_id": project_id or "",
        "collection_id": collection_id or "default",
        "window_hours": window_hours,
        "period": period,
        "sku": "L1",
        "daemon": daemon,
        "cost": cost,
        "kb_health": kb,
        "spec": "packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md §5 L1",
    }


def render_monthly_ops_markdown(report: Dict[str, Any]) -> str:
    """Customer-facing monthly ops page (Chinese; no invented metrics)."""
    cost = report.get("cost") or {}
    kb = report.get("kb_health") or {}
    daemon = report.get("daemon") or {}
    cache = cost.get("cache") or {}
    api = cost.get("api_calls") or {}
    routing = cost.get("model_routing") or {}
    empty = cost.get("empty_intercept") or {}
    health = kb.get("health") or {}
    metrics = kb.get("metrics") or {}
    tips = kb.get("suggestions") or []

    lines: List[str] = [
        f"# 月度运行报告（{report.get('period') or '-'}）",
        "",
        f"> 租户 `{report.get('tenant_id')}` · 窗口 {report.get('window_hours')}h · "
        f"SKU {report.get('sku')} · 生成于 {report.get('generated_at')}",
        "",
        "## 1. 存活与托管",
        "",
    ]
    if daemon.get("available"):
        lines.append(
            f"- **托管任务**: {daemon.get('running_jobs', 0)} 运行中 / "
            f"共 {daemon.get('total_jobs', 0)} 个"
            f"（{daemon.get('note') or 'daemon_jobs'}）"
        )
    else:
        lines.append(
            f"- **托管任务**: unavailable（{daemon.get('reason', 'n/a')}）；"
            "平台 daemon_jobs 未接线时跳过，不编造存活率"
        )

    lines.extend(["", "## 2. 调用与成本", ""])
    if api.get("available") and api.get("total") is not None:
        lines.append(f"- **API / 检索调用**: {api.get('total')} 次")
    else:
        lines.append("- **API / 检索调用**: unavailable")
    if cache.get("available"):
        rate = cache.get("hit_rate_pct")
        rate_s = f"{rate}%" if rate is not None else "n/a"
        lines.append(
            f"- **缓存命中**: {cache.get('hits', 0)} / {cache.get('total_requests', 0)}"
            f"（命中率 {rate_s}）"
        )
    else:
        lines.append(f"- **缓存命中**: unavailable（{cache.get('reason', 'n/a')}）")
    if routing.get("usage_share_available"):
        src = routing.get("usage_share_source") or ""
        unit = "完成调用" if src == "llm_syscall" else "选择次数"
        bucket = routing.get("bucket_share_pct") or {}
        lines.append(
            f"- **模型分流占比**（{unit}，合计 {routing.get('selection_total', 0)}）: "
            f"简单 {bucket.get('simple', 0)}% · 复杂 {bucket.get('complex', 0)}% · "
            f"其他 {bucket.get('other', 0)}%"
        )
    else:
        lines.append(
            f"- **模型分流占比**: unavailable（{routing.get('usage_share_note') or '无计量'}）"
        )
    if empty.get("available") and empty.get("count") is not None:
        lines.append(f"- **空检索拦截**: {empty.get('count')} 次")
    else:
        lines.append("- **空检索拦截**: unavailable")

    lines.extend(["", "## 3. 知识库健康", ""])
    if health.get("insufficient_data") or health.get("score") is None:
        lines.append(
            f"- **健康分**: —/100（{health.get('label') or '数据不足'}；不编造分数）"
        )
    else:
        lines.append(
            f"- **健康分**: {health.get('score')}/100（{health.get('label') or '-'}）"
        )
    if metrics.get("available") is False:
        lines.append(f"- **检索指标**: unavailable（{metrics.get('reason', 'n/a')}）")
    else:
        lines.append(
            f"- **本窗查询**: {metrics.get('total_queries', 'n/a')} · "
            f"无答案率 {metrics.get('no_answer_rate_pct', 'n/a')}% · "
            f"引用覆盖 {metrics.get('citation_coverage_pct', 'n/a')}%"
        )

    lines.extend(["", "## 4. 运营建议", ""])
    if tips:
        for i, tip in enumerate(tips[:5], 1):
            lines.append(f"{i}. {tip}")
    else:
        lines.append("1. 维持当前巡检与入库节奏；有漏召 TOP 时优先补文档。")
    lines.extend(
        [
            "",
            "## 叙事要点",
            "",
            "1. L1 托管先讲**存活 + 调用量 + 缓存命中**，再谈 token/模型。",
            "2. 健康分与分流占比无数据时标明 unavailable，不编造。",
            "3. 明细见同包 `COST_REPORT.md` / `KB_HEALTH.md`。",
            "",
        ]
    )
    return "\n".join(lines)


def monthly_ops_summary_lines(report: Dict[str, Any]) -> str:
    """Short summary for Pi slash / ops dashboards."""
    cost = report.get("cost") or {}
    kb = report.get("kb_health") or {}
    daemon = report.get("daemon") or {}
    cache = cost.get("cache") or {}
    api = cost.get("api_calls") or {}
    health = kb.get("health") or {}
    tips = kb.get("suggestions") or []
    if health.get("insufficient_data") or health.get("score") is None:
        score_line = f"知识库健康分: —/100（{health.get('label') or '数据不足'}）"
    else:
        score_line = f"知识库健康分: {health.get('score')}/100"
    daemon_line = (
        f"托管任务: {daemon.get('running_jobs', 0)}/{daemon.get('total_jobs', 0)} 运行中"
        if daemon.get("available")
        else "托管任务: unavailable"
    )
    calls = api.get("total") if api.get("available") else "n/a"
    hit = cache.get("hit_rate_pct") if cache.get("available") else None
    hit_s = f"{hit}%" if hit is not None else "n/a"
    return "\n".join(
        [
            f"月度运行报告 {report.get('period') or ''}".strip(),
            daemon_line,
            f"调用 {calls} 次 | 缓存命中率 {hit_s}",
            score_line,
            f"建议: {(tips[0] if tips else '维持巡检与入库节奏')}",
        ]
    )
