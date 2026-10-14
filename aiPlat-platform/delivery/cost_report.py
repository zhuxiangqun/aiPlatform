"""Delivery cost narrative page (HYBRID_ENTERPRISE_DELIVERY §4).

Aggregates existing meters — does not invent ¥ savings without a price table.
Model routing shows **policy snapshot** (purpose→model); usage % is unavailable
until a call-by-purpose meter exists.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lightweight / heavy purpose buckets for customer language (not usage counts).
_SIMPLE_PURPOSES = ("chat", "clarify", "skill_execution")
_COMPLEX_PURPOSES = ("code_gen", "reasoning", "doc_llm", "eval_code")


def _cache_stats() -> Dict[str, Any]:
    try:
        from core.api.core_facade import get_semantic_cache

        cache = get_semantic_cache()
        raw = cache.stats if hasattr(cache, "stats") else {}
        if callable(raw):
            raw = raw()
        if not isinstance(raw, dict):
            return {"available": False, "reason": "stats_not_dict"}
        hits = int(raw.get("l1_hits") or 0) + int(raw.get("l2_hits") or 0)
        misses = int(raw.get("misses") or 0)
        total = int(raw.get("total_requests") or (hits + misses))
        rate = None
        hr = raw.get("hit_rate")
        if isinstance(hr, str) and hr.endswith("%"):
            try:
                rate = float(hr.rstrip("%"))
            except ValueError:
                rate = None
        elif total > 0:
            rate = round(100.0 * hits / total, 1)
        return {
            "available": True,
            "l1_hits": int(raw.get("l1_hits") or 0),
            "l2_hits": int(raw.get("l2_hits") or 0),
            "misses": misses,
            "hits": hits,
            "total_requests": total,
            "hit_rate_pct": rate,
            "enabled": bool(getattr(cache, "enabled", True)),
        }
    except Exception as e:
        logger.debug("cost_report cache stats: %s", e, exc_info=True)
        return {"available": False, "reason": str(e)}


def kb_cache_stats(*, tenant_id: str = "default") -> Dict[str, Any]:
    """Public cache stats for ``GET /platform/kb/cache-stats`` (KB_HEALTH §3.2.3).

    ``tenant_id`` reserved for future tenancy; semantic_cache is process-local today.
    """
    _ = tenant_id
    raw = _cache_stats()
    out = dict(raw)
    if out.get("available"):
        hits = int(out.get("hits") or 0)
        out["cache_hits"] = hits
        out["estimated_saved_calls"] = hits
    return out


def _kb_metrics(tenant_id: str = "", hours: int = 720) -> Dict[str, Any]:
    """Prefer platform kb.metrics; soft-fail to empty."""
    try:
        from kb.metrics import get_kb_metrics

        m = get_kb_metrics(window_hours=hours, tenant_id=tenant_id or "")
        if not isinstance(m, dict):
            return {"available": False}
        return {
            "available": True,
            "total_queries": int(m.get("total_queries") or 0),
            "no_answer_rate_pct": m.get("no_answer_rate_pct"),
            "citation_coverage_pct": m.get("citation_coverage_pct"),
            "window_hours": hours,
        }
    except Exception as e:
        logger.debug("cost_report kb metrics: %s", e, exc_info=True)
        return {"available": False, "reason": str(e)}


def _billing_snapshot(tenant_id: str = "default") -> Dict[str, Any]:
    try:
        from datetime import datetime as _dt

        from storage.platform_db import get_platform_db

        now = _dt.now()
        db = get_platform_db()
        breakdown = db.get_monthly_breakdown(tenant_id or "default", now.year, now.month)
        total_cents = sum(int(r.get("cost") or r.get("cost_cents") or 0) for r in (breakdown or []))
        tokens = sum(int(r.get("tokens") or r.get("tokens_used") or 0) for r in (breakdown or []))
        return {
            "available": True,
            "period": f"{now.year}-{now.month:02d}",
            "total_cost_cents": total_cents,
            "tokens_used": tokens,
            "breakdown": breakdown or [],
        }
    except Exception as e:
        logger.debug("cost_report billing: %s", e, exc_info=True)
        return {"available": False, "reason": str(e)}


def _model_routing_policy() -> Dict[str, Any]:
    """Configured purpose→model map (not live traffic share)."""
    purposes = list(dict.fromkeys(_SIMPLE_PURPOSES + _COMPLEX_PURPOSES + ("agent",)))
    mapping: Dict[str, str] = {}
    try:
        from core.api.core_facade import best_model_for_purpose
    except Exception as e:
        return {"available": False, "reason": str(e), "usage_share_available": False}
    for p in purposes:
        try:
            mapping[p] = str(best_model_for_purpose(p) or "")
        except Exception:
            mapping[p] = ""
    return {
        "available": True,
        "usage_share_available": False,
        "usage_share_note": "尚无按 purpose 的调用计量；下列为当前分流策略（配置快照），非流量占比",
        "simple_purposes": list(_SIMPLE_PURPOSES),
        "complex_purposes": list(_COMPLEX_PURPOSES),
        "purpose_to_model": mapping,
    }


def _optional_cny_saved(cache: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Only when AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT is set — never invent ¥."""
    raw = os.environ.get("AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT", "").strip()
    if not raw:
        return None
    try:
        per_hit = float(raw)
    except ValueError:
        return None
    if per_hit <= 0 or not cache.get("available"):
        return None
    hits = int(cache.get("hits") or 0)
    return {
        "cny_per_cache_hit": per_hit,
        "estimated_saved_cny": round(hits * per_hit, 2),
        "note": "估算值 = 缓存命中次数 × AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT；非账单权威",
    }


def build_delivery_cost_report(
    *,
    tenant_id: str = "default",
    window_hours: int = 720,
    project_id: str = "",
) -> Dict[str, Any]:
    cache = _cache_stats()
    kb = _kb_metrics(tenant_id=tenant_id, hours=window_hours)
    billing = _billing_snapshot(tenant_id=tenant_id)
    routing = _model_routing_policy()
    cny = _optional_cny_saved(cache)

    api_calls = None
    if billing.get("available") and (billing.get("breakdown") or billing.get("tokens_used")):
        # Prefer request count from breakdown if present
        reqs = 0
        for r in billing.get("breakdown") or []:
            reqs += int(r.get("requests") or r.get("count") or 0)
        if reqs:
            api_calls = reqs
    if api_calls is None and kb.get("available"):
        api_calls = int(kb.get("total_queries") or 0)

    empty_intercept = {
        "available": False,
        "reason": "专用无效请求拦截计数尚未接线",
        "proxy": None,
    }
    if kb.get("available") and kb.get("no_answer_rate_pct") is not None:
        empty_intercept = {
            "available": False,
            "reason": "专用拦截计数待补；暂用 KB 无答案率作参考（非同一指标）",
            "proxy": {
                "label": "kb_no_answer_rate_pct",
                "value": kb.get("no_answer_rate_pct"),
            },
        }

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id or "default",
        "project_id": project_id or "",
        "window_hours": window_hours,
        "api_calls": {
            "available": api_calls is not None,
            "total": api_calls,
            "source": "billing_breakdown" if billing.get("available") and api_calls else "kb_metrics.total_queries",
        },
        "cache": cache,
        "model_routing": routing,
        "empty_intercept": empty_intercept,
        "billing": billing,
        "kb_metrics": kb,
        "cny_estimate": cny,
        "spec": "packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_DELIVERY.md §4",
    }


def render_cost_report_markdown(report: Dict[str, Any]) -> str:
    """Customer-facing cost page (Chinese narrative; no fake ¥)."""
    cache = report.get("cache") or {}
    api = report.get("api_calls") or {}
    routing = report.get("model_routing") or {}
    billing = report.get("billing") or {}
    empty = report.get("empty_intercept") or {}
    cny = report.get("cny_estimate")
    lines: List[str] = [
        "# 交付报告 · 成本页",
        "",
        f"> 生成时间: {report.get('generated_at', '')}  ",
        f"> 租户: `{report.get('tenant_id', '-')}`  "
        f"项目: `{report.get('project_id') or '-'}`  "
        f"窗口: {report.get('window_hours', '')}h",
        "",
        "规格: `HYBRID_ENTERPRISE_DELIVERY.md` §4",
        "",
        "## 本月用量（客户可见）",
        "",
    ]

    if api.get("available") and api.get("total") is not None:
        lines.append(f"- **API / 知识查询调用总量**: {api['total']} 次（来源: {api.get('source', '')}）")
    else:
        lines.append("- **API 调用总量**: 暂无计量出口（unavailable）")

    if cache.get("available"):
        rate = cache.get("hit_rate_pct")
        rate_s = f"{rate}%" if rate is not None else "n/a"
        lines.append(
            f"- **缓存命中**: {cache.get('hits', 0)} 次命中 / "
            f"{cache.get('total_requests', 0)} 次请求（命中率 {rate_s}；"
            f"L1={cache.get('l1_hits', 0)}, L2={cache.get('l2_hits', 0)}, miss={cache.get('misses', 0)}）"
        )
    else:
        lines.append(f"- **缓存命中率**: unavailable（{cache.get('reason', 'n/a')}）")

    if cny:
        lines.append(
            f"- **缓存节省估算**: ¥{cny.get('estimated_saved_cny')} "
            f"（{cny.get('note', '')}）"
        )
    else:
        lines.append(
            "- **缓存节省 ¥**: 未配置单价（设置 `AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT` 后显示；"
            "无价目表不编造金额）"
        )

    if billing.get("available"):
        cents = int(billing.get("total_cost_cents") or 0)
        if cents > 0:
            lines.append(
                f"- **账单合计**: ¥{cents / 100:.2f}（period={billing.get('period')}；"
                f"来自 billing_records，非估算）"
            )
        else:
            lines.append(
                f"- **账单合计**: period={billing.get('period')} 暂无记录 "
                f"（tokens={billing.get('tokens_used', 0)}）"
            )
    else:
        lines.append("- **账单**: unavailable")

    lines.extend(["", "## 模型分流策略（配置快照）", ""])
    if routing.get("available"):
        lines.append(f"> {routing.get('usage_share_note', '')}")
        lines.append("")
        lines.append("| 用途 (purpose) | 选用模型 | 档位 |")
        lines.append("|----------------|----------|------|")
        simple = set(routing.get("simple_purposes") or [])
        complex_ = set(routing.get("complex_purposes") or [])
        for p, m in (routing.get("purpose_to_model") or {}).items():
            tier = "简单/轻量" if p in simple else ("复杂/推理" if p in complex_ else "其他")
            lines.append(f"| `{p}` | `{m or '-'}` | {tier} |")
        lines.append("")
        lines.append(
            "说明：简单问题走轻量模型、复杂问题走推理/代码模型——"
            "**流量占比需按 purpose 计量后补**，当前不展示虚假百分比。"
        )
    else:
        lines.append(f"- 分流策略 unavailable（{routing.get('reason', 'n/a')}）")

    lines.extend(["", "## 无效请求 / 空检索", ""])
    proxy = empty.get("proxy")
    if proxy:
        lines.append(
            f"- 专用拦截计数: **待补**（{empty.get('reason', '')}）"
        )
        lines.append(
            f"- 参考指标 `{proxy.get('label')}`: {proxy.get('value')} "
            "（KB 无答案率，不等于拦截次数）"
        )
    else:
        lines.append(f"- {empty.get('reason', 'unavailable')}")

    lines.extend(
        [
            "",
            "## 叙事要点（交付话术）",
            "",
            "1. 客户问「一个月花多少」→ 优先给**调用次数 + 缓存命中率**，避免只甩 token 术语。",
            "2. 有账单记录时展示权威 ¥；仅有单价 env 时标注「估算」。",
            "3. 模型分流讲「简单/复杂策略」，在计量出口就绪前不编造占比。",
            "",
        ]
    )
    return "\n".join(lines)
