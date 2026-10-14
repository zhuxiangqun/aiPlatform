"""L3 duty desk (HYBRID_ENTERPRISE_DELIVERY §5 SKU L3).

Customer-visible on-call entry: contact channel + eval observability +
miss/low-confidence signals as iteration cues + derived quarterly tips.
Soft-fails every subsystem; never invents scores or fake iteration history.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _duty_contact() -> Dict[str, Any]:
    contact = (os.environ.get("AIPLAT_L3_DUTY_CONTACT") or "").strip()
    channel = (os.environ.get("AIPLAT_L3_DUTY_CHANNEL") or "").strip()
    hours = (os.environ.get("AIPLAT_L3_DUTY_HOURS") or "").strip()
    if not contact and not channel:
        return {
            "available": False,
            "reason": "未配置 AIPLAT_L3_DUTY_CONTACT / AIPLAT_L3_DUTY_CHANNEL",
        }
    return {
        "available": True,
        "contact": contact or None,
        "channel": channel or None,
        "hours": hours or "按托管协议 SLA",
        "note": "专属值班入口（环境变量配置；未设则不编造联系人）",
    }


def _eval_snapshot() -> Dict[str, Any]:
    try:
        from governance.eval_observability import aggregate

        view = aggregate()
        if not isinstance(view, dict):
            return {"available": False, "reason": "aggregate_not_dict"}
        exp = view.get("experiences") or {}
        et = view.get("evidence_tree")
        gt = view.get("guard_trace")
        sources = view.get("sources") or []
        present_n = sum(1 for s in sources if isinstance(s, dict) and s.get("present"))
        return {
            "available": True,
            "sources_present": present_n,
            "sources_total": len(sources),
            "evidence_tree": et,
            "guard_trace": gt,
            "experiences": {
                "count": int(exp.get("count") or 0),
                "by_status": exp.get("by_status") or {},
                "recent": list(exp.get("recent") or [])[:5],
            },
            "org_harness_ok": bool(
                isinstance(view.get("org_harness"), dict)
                and (view.get("org_harness") or {}).get("ok")
            ),
        }
    except Exception as e:
        logger.debug("l3_duty eval snapshot: %s", e, exc_info=True)
        return {"available": False, "reason": str(e)}


def _kb_signals(*, tenant_id: str, window_hours: int) -> Dict[str, Any]:
    try:
        from delivery.kb_health import kb_low_confidence_top, kb_miss_top

        miss = kb_miss_top(tenant_id=tenant_id, window_hours=window_hours, limit=5)
        low = kb_low_confidence_top(
            tenant_id=tenant_id, window_hours=window_hours, limit=5
        )
        return {
            "available": bool(miss.get("available") or low.get("available")),
            "miss_top": miss,
            "low_confidence_top": low,
        }
    except Exception as e:
        logger.debug("l3_duty kb signals: %s", e, exc_info=True)
        return {"available": False, "reason": str(e)}


def _iteration_records(eval_snap: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort iteration log from experience feedback recent rows."""
    if not eval_snap.get("available"):
        return {
            "available": False,
            "items": [],
            "reason": eval_snap.get("reason") or "eval unavailable",
        }
    recent = ((eval_snap.get("experiences") or {}).get("recent")) or []
    items: List[Dict[str, Any]] = []
    for row in recent:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "id": row.get("id") or row.get("experience_id") or "",
                "status": row.get("status") or "pending",
                "title": str(
                    row.get("title")
                    or row.get("summary")
                    or row.get("lesson")
                    or row.get("text")
                    or ""
                )[:200],
                "updated_at": row.get("updated_at") or row.get("created_at") or "",
            }
        )
    if not items:
        return {
            "available": False,
            "items": [],
            "reason": "暂无经验回写/迭代记录（AIPLAT_EXPERIENCE_FILE 空或不存在）",
        }
    return {"available": True, "items": items, "count": len(items)}


def _quarterly_suggestions(
    *,
    contact: Dict[str, Any],
    eval_snap: Dict[str, Any],
    signals: Dict[str, Any],
    iterations: Dict[str, Any],
) -> List[str]:
    tips: List[str] = []
    if not contact.get("available"):
        tips.append(
            "开通 L3 时配置 AIPLAT_L3_DUTY_CONTACT（及可选 CHANNEL/HOURS），"
            "客户即可在值班页看到专属入口。"
        )
    miss = (signals.get("miss_top") or {}).get("items") or []
    if miss:
        tip_q = str((miss[0] or {}).get("question") or (miss[0] or {}).get("q") or "")[:60]
        if tip_q:
            tips.append(f"本季优先补文档覆盖漏召 TOP：「{tip_q}」")
        else:
            tips.append("本季优先消化漏召 TOP 清单，补齐高频未命中主题文档。")
    low = (signals.get("low_confidence_top") or {}).get("items") or []
    if low:
        tips.append("低置信回答 TOP 纳入小版本迭代：收紧检索或补充权威出处。")
    et = eval_snap.get("evidence_tree") if eval_snap.get("available") else None
    if isinstance(et, dict) and et.get("present") and et.get("known_gaps"):
        gaps = et.get("known_gaps") or []
        if gaps:
            tips.append(f"证据树已知缺口 {len(gaps)} 项，纳入季度治理复盘。")
    gt = eval_snap.get("guard_trace") if eval_snap.get("available") else None
    if isinstance(gt, dict) and gt.get("present") and gt.get("failed_guards"):
        tips.append("守卫失败项进入值班板跟踪，避免回归。")
    if iterations.get("available"):
        tips.append("经验回写有待审条目时，值班侧优先晋升/驳回，形成迭代闭环。")
    if not tips:
        tips.append("维持 L2 入库与巡检；有漏召/低置信信号后再开小版本迭代。")
    return tips[:6]


def build_l3_duty_desk(
    *,
    tenant_id: str = "default",
    window_hours: int = 720,
    project_id: str = "",
) -> Dict[str, Any]:
    contact = _duty_contact()
    eval_snap = _eval_snapshot()
    signals = _kb_signals(tenant_id=tenant_id, window_hours=min(int(window_hours), 168))
    iterations = _iteration_records(eval_snap)
    tips = _quarterly_suggestions(
        contact=contact,
        eval_snap=eval_snap,
        signals=signals,
        iterations=iterations,
    )
    quarter = datetime.now(timezone.utc).strftime("%Y-Q") + str(
        (datetime.now(timezone.utc).month - 1) // 3 + 1
    )
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id or "default",
        "project_id": project_id or "",
        "window_hours": window_hours,
        "period": quarter,
        "sku": "L3",
        "duty_contact": contact,
        "eval": eval_snap,
        "kb_signals": signals,
        "iterations": iterations,
        "quarterly_suggestions": tips,
        "spec": "packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md §5 L3",
    }


def render_l3_duty_markdown(report: Dict[str, Any]) -> str:
    contact = report.get("duty_contact") or {}
    eval_snap = report.get("eval") or {}
    signals = report.get("kb_signals") or {}
    iterations = report.get("iterations") or {}
    tips = report.get("quarterly_suggestions") or []

    lines: List[str] = [
        f"# L3 专属值班台（{report.get('period') or '-'}）",
        "",
        f"> 租户 `{report.get('tenant_id')}` · 窗口 {report.get('window_hours')}h · "
        f"SKU {report.get('sku')} · 生成于 {report.get('generated_at')}",
        "",
        "## 1. 专属值班入口",
        "",
    ]
    if contact.get("available"):
        if contact.get("contact"):
            lines.append(f"- **联系人/邮箱**: {contact.get('contact')}")
        if contact.get("channel"):
            lines.append(f"- **通道**: {contact.get('channel')}")
        lines.append(f"- **值守时段**: {contact.get('hours') or '按托管协议 SLA'}")
    else:
        lines.append(
            f"- **值班入口**: unavailable（{contact.get('reason', 'n/a')}）；"
            "开通时配置环境变量，不编造联系人"
        )

    lines.extend(["", "## 2. 评测与治理观测", ""])
    if eval_snap.get("available"):
        lines.append(
            f"- **观测源**: {eval_snap.get('sources_present', 0)}/"
            f"{eval_snap.get('sources_total', 0)} 可用"
        )
        et = eval_snap.get("evidence_tree")
        if isinstance(et, dict) and et.get("present"):
            lines.append(
                f"- **证据树**: verdict={et.get('verdict') or 'n/a'} · "
                f"gaps={len(et.get('known_gaps') or [])}"
            )
        else:
            lines.append("- **证据树**: unavailable")
        gt = eval_snap.get("guard_trace")
        if isinstance(gt, dict) and gt.get("present"):
            failed = gt.get("failed_guards") or []
            lines.append(
                f"- **守卫轨迹**: verdict={gt.get('verdict') or 'n/a'} · "
                f"failed={len(failed)}"
            )
        else:
            lines.append("- **守卫轨迹**: unavailable")
        exp = eval_snap.get("experiences") or {}
        lines.append(
            f"- **经验回写**: {exp.get('count', 0)} 条 · 状态 {exp.get('by_status') or {}}"
        )
    else:
        lines.append(
            f"- **评测观测**: unavailable（{eval_snap.get('reason', 'n/a')}）"
        )

    lines.extend(["", "## 3. 迭代信号（漏召 / 低置信）", ""])
    miss = (signals.get("miss_top") or {}) if signals.get("available") else {}
    low = (signals.get("low_confidence_top") or {}) if signals.get("available") else {}
    if miss.get("available") and (miss.get("items") or []):
        lines.append("- **漏召 TOP**:")
        for it in (miss.get("items") or [])[:5]:
            q = it.get("question") or it.get("q") or it.get("text") or "-"
            lines.append(f"  - {str(q)[:120]}")
    else:
        lines.append(
            f"- **漏召 TOP**: unavailable（{(miss or {}).get('reason') or signals.get('reason') or 'n/a'}）"
        )
    if low.get("available") and (low.get("items") or []):
        lines.append("- **低置信 TOP**:")
        for it in (low.get("items") or [])[:5]:
            q = it.get("question") or it.get("q") or it.get("text") or "-"
            sc = it.get("score")
            sc_s = f" score={sc}" if sc is not None else ""
            lines.append(f"  - {str(q)[:120]}{sc_s}")
    else:
        lines.append(
            f"- **低置信 TOP**: unavailable（{(low or {}).get('reason') or signals.get('reason') or 'n/a'}）"
        )

    lines.extend(["", "## 4. 迭代记录", ""])
    if iterations.get("available"):
        for it in iterations.get("items") or []:
            title = it.get("title") or "(无标题)"
            lines.append(
                f"- [{it.get('status')}] {title}"
                + (f" · {it.get('updated_at')}" if it.get("updated_at") else "")
            )
    else:
        lines.append(
            f"- unavailable（{iterations.get('reason', 'n/a')}）；"
            "有经验回写文件后自动出现"
        )

    lines.extend(["", "## 5. 季度建议", ""])
    for i, tip in enumerate(tips[:6], 1):
        lines.append(f"{i}. {tip}")
    lines.extend(
        [
            "",
            "## 叙事要点",
            "",
            "1. L3 = **专属值班入口 + 迭代记录 + 季度建议**，底层仍是 Quality Bus / eval / 值班板。",
            "2. 联系人与迭代史无配置/无数据时标明 unavailable，不编造。",
            "3. 漏召/低置信信号直接变成运营动作，支撑续费与小版本迭代。",
            "",
        ]
    )
    return "\n".join(lines)


def l3_duty_summary_lines(report: Dict[str, Any]) -> str:
    contact = report.get("duty_contact") or {}
    tips = report.get("quarterly_suggestions") or []
    iterations = report.get("iterations") or {}
    eval_snap = report.get("eval") or {}
    if contact.get("available"):
        entry = contact.get("contact") or contact.get("channel") or "已配置"
        contact_line = f"值班入口: {entry}"
    else:
        contact_line = "值班入口: unavailable（未配置联系通道）"
    if iterations.get("available"):
        iter_line = f"迭代记录: {iterations.get('count', 0)} 条"
    else:
        iter_line = "迭代记录: unavailable"
    src = (
        f"观测源 {eval_snap.get('sources_present', 0)}/{eval_snap.get('sources_total', 0)}"
        if eval_snap.get("available")
        else "观测源 unavailable"
    )
    return "\n".join(
        [
            f"L3 专属值班台 {report.get('period') or ''}".strip(),
            contact_line,
            iter_line,
            src,
            f"建议: {(tips[0] if tips else '维持巡检与入库节奏')}",
        ]
    )
