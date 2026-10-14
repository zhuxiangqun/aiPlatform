"""Delivery cost narrative page (HYBRID_ENTERPRISE_DELIVERY §4).

Aggregates existing meters — does not invent ¥ savings without a price table.
Model routing shows **policy snapshot** (purpose→model) plus usage share:
prefer LLM syscall completions with ``args.purpose``; else fall back to
``model_selection_log`` selection counts. Missing both → no fake percentages.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lightweight / heavy purpose buckets for customer language (not usage counts).
_SIMPLE_PURPOSES = ("chat", "clarify", "skill_execution")
_COMPLEX_PURPOSES = ("code_gen", "reasoning", "doc_llm", "eval_code")
# Adapter factory noise — not routing traffic.
_SKIP_PURPOSES = frozenset({"create_adapter", ""})
_SKIP_ENTRIES = frozenset({"create_selected_adapter"})


def _selection_log_path() -> str:
    home = os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat"))
    return os.path.join(home, "wiki", "model_selection_log.json")


def _empty_usage(window_hours: int, *, note: str = "", source: str = "") -> Dict[str, Any]:
    return {
        "usage_share_available": False,
        "usage_share_note": note,
        "usage_share_source": source,
        "purpose_counts": {},
        "purpose_share_pct": {},
        "bucket_share_pct": {},
        "bucket_counts": {},
        "selection_total": 0,
        "window_hours": window_hours,
    }


def _share_from_counts(
    counts: Dict[str, int],
    *,
    window_hours: int,
    source: str,
    note: str,
) -> Dict[str, Any]:
    total = sum(counts.values())
    if total <= 0:
        return _empty_usage(window_hours, note=note, source=source)
    share = {
        p: round(100.0 * c / total, 1)
        for p, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    }
    simple_n = sum(int(counts.get(p, 0)) for p in _SIMPLE_PURPOSES)
    complex_n = sum(int(counts.get(p, 0)) for p in _COMPLEX_PURPOSES)
    other_n = max(0, total - simple_n - complex_n)
    return {
        "usage_share_available": True,
        "usage_share_note": note,
        "usage_share_source": source,
        "purpose_counts": dict(sorted(counts.items(), key=lambda x: (-x[1], x[0]))),
        "purpose_share_pct": share,
        "bucket_share_pct": {
            "simple": round(100.0 * simple_n / total, 1),
            "complex": round(100.0 * complex_n / total, 1),
            "other": round(100.0 * other_n / total, 1),
        },
        "bucket_counts": {
            "simple": simple_n,
            "complex": complex_n,
            "other": other_n,
        },
        "selection_total": total,
        "window_hours": window_hours,
    }


def _purpose_usage_from_llm_syscalls(window_hours: int = 720) -> Dict[str, Any]:
    """Count successful llm generate events that stamped args.purpose."""
    empty_note = (
        f"窗口 {window_hours}h 内尚无带 purpose 的 LLM 完成调用；"
        "将回退 model_selection_log"
    )
    try:
        import sqlite3

        from delivery.kb_health import _execution_db_path

        db_path = _execution_db_path()
        if not db_path:
            return _empty_usage(window_hours, note=empty_note, source="llm_syscall")
        cutoff = time.time() - max(1, int(window_hours)) * 3600.0
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT args_json FROM syscall_events
                WHERE kind = 'llm'
                  AND status = 'success'
                  AND created_at > ?
                  AND COALESCE(args_json, '') LIKE '%"purpose"%'
                ORDER BY created_at DESC
                LIMIT 5000
                """,
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()
        counts: Dict[str, int] = {}
        for (args_json,) in rows or []:
            try:
                blob = json.loads(args_json) if isinstance(args_json, str) else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(blob, dict):
                continue
            purpose = str(blob.get("purpose") or "").strip()
            if purpose in _SKIP_PURPOSES:
                continue
            counts[purpose] = counts.get(purpose, 0) + 1
        if not counts:
            return _empty_usage(window_hours, note=empty_note, source="llm_syscall")
        return _share_from_counts(
            counts,
            window_hours=window_hours,
            source="llm_syscall",
            note=(
                "占比来自 syscall_events（kind=llm status=success 且 args.purpose；"
                "LLM 完成调用次数）"
            ),
        )
    except Exception as e:
        logger.debug("cost_report llm purpose share: %s", e, exc_info=True)
        return _empty_usage(
            window_hours,
            note=f"读取 LLM syscall purpose 失败（{e}）",
            source="llm_syscall",
        )


def _purpose_usage_from_selection_log(window_hours: int = 720) -> Dict[str, Any]:
    """Aggregate model_selection_log by purpose (selection counts, not completions)."""
    path = _selection_log_path()
    if not os.path.isfile(path):
        return _empty_usage(
            window_hours,
            note="尚无 model_selection_log；下列为分流策略配置快照，非流量占比",
            source="model_selection_log",
        )
    try:
        with open(path, encoding="utf-8") as f:
            samples = json.load(f)
        if not isinstance(samples, list):
            return _empty_usage(
                window_hours,
                note="model_selection_log 格式异常；下列为配置快照",
                source="model_selection_log",
            )
        cutoff = time.time() - max(1, int(window_hours)) * 3600.0
        counts: Dict[str, int] = {}
        for rec in samples:
            if not isinstance(rec, dict):
                continue
            purpose = str(rec.get("purpose") or "").strip()
            entry = str(rec.get("entry") or "")
            if purpose in _SKIP_PURPOSES or entry in _SKIP_ENTRIES:
                continue
            try:
                ts_f = float(rec.get("ts"))
            except (TypeError, ValueError):
                continue
            if ts_f < cutoff:
                continue
            counts[purpose] = counts.get(purpose, 0) + 1
        if not counts:
            return _empty_usage(
                window_hours,
                note=(
                    f"窗口 {window_hours}h 内无 purpose 选择记录；"
                    "下列为配置快照，非流量占比"
                ),
                source="model_selection_log",
            )
        return _share_from_counts(
            counts,
            window_hours=window_hours,
            source="model_selection_log",
            note=(
                "占比来自 model_selection_log（best_model_for_purpose / "
                "get_default_model 选择次数；窗口内尚无带 purpose 的 LLM 完成调用）"
            ),
        )
    except Exception as e:
        logger.debug("cost_report selection-log purpose share: %s", e, exc_info=True)
        return _empty_usage(
            window_hours,
            note=f"读取 model_selection_log 失败（{e}）；下列为配置快照",
            source="model_selection_log",
        )


def _purpose_usage_share(window_hours: int = 720) -> Dict[str, Any]:
    """Prefer LLM completion purpose share; fall back to selection log."""
    llm = _purpose_usage_from_llm_syscalls(window_hours=window_hours)
    if llm.get("usage_share_available"):
        return llm
    sel = _purpose_usage_from_selection_log(window_hours=window_hours)
    if sel.get("usage_share_available"):
        return sel
    note = sel.get("usage_share_note") or llm.get("usage_share_note") or (
        "尚无按 purpose 的计量；下列为分流策略配置快照，非流量占比"
    )
    return _empty_usage(window_hours, note=note, source=sel.get("usage_share_source") or "")


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
            "empty_retrieve_count": int(m.get("empty_retrieve_count") or 0),
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


def _purpose_models_from_selection_log(
    purposes: List[str],
    window_hours: int = 720,
) -> Dict[str, str]:
    """Latest selected model per purpose from model_selection_log (newest first)."""
    path = _selection_log_path()
    if not os.path.isfile(path):
        return {}
    want = set(purposes)
    try:
        with open(path, encoding="utf-8") as f:
            samples = json.load(f)
        if not isinstance(samples, list):
            return {}
        cutoff = time.time() - max(1, int(window_hours)) * 3600.0
        latest: Dict[str, str] = {}
        for rec in reversed(samples):
            if not isinstance(rec, dict):
                continue
            purpose = str(rec.get("purpose") or "").strip()
            entry = str(rec.get("entry") or "")
            if purpose not in want or purpose in _SKIP_PURPOSES or entry in _SKIP_ENTRIES:
                continue
            if purpose in latest:
                continue
            try:
                ts_f = float(rec.get("ts"))
            except (TypeError, ValueError):
                continue
            if ts_f < cutoff:
                continue
            selected = str(rec.get("selected") or "").strip()
            if selected:
                latest[purpose] = selected
        return latest
    except Exception as e:
        logger.debug("cost_report purpose→model from selection log: %s", e, exc_info=True)
        return {}


def _model_routing_policy(window_hours: int = 720) -> Dict[str, Any]:
    """Configured purpose→model map + best-effort selection-log usage share.

    Usage share is independent of model resolution: if ``best_model_for_purpose``
    fails (e.g. runtime typing), still show purpose/档位占比 when the log exists.
    Empty model cells are backfilled from the latest selection-log pick per purpose.
    """
    # Read share before best_model_for_purpose so this report does not self-inflate counts.
    usage = _purpose_usage_share(window_hours=window_hours)
    purposes = list(dict.fromkeys(_SIMPLE_PURPOSES + _COMPLEX_PURPOSES + ("agent",)))
    mapping: Dict[str, str] = {}
    map_err: Optional[str] = None
    map_source = "best_model_for_purpose"
    bmp = None
    try:
        from core.api.core_facade import best_model_for_purpose as bmp  # noqa: N813
    except Exception as e:
        map_err = str(e)
        bmp = None
    if bmp is not None:
        for p in purposes:
            try:
                mapping[p] = str(bmp(p) or "")
            except Exception:
                mapping[p] = ""
    if not mapping:
        mapping = {p: "" for p in purposes}
    live_filled = sum(1 for p in purposes if (mapping.get(p) or "").strip())
    log_map = _purpose_models_from_selection_log(purposes, window_hours=window_hours)
    filled_from_log = 0
    for p in purposes:
        if not (mapping.get(p) or "").strip() and log_map.get(p):
            mapping[p] = log_map[p]
            filled_from_log += 1
    if live_filled and filled_from_log:
        map_source = "mixed"
    elif filled_from_log and not live_filled:
        map_source = "model_selection_log"
    elif live_filled:
        map_source = "best_model_for_purpose"
    else:
        map_source = "none"
    note = usage.get("usage_share_note") or ""
    if not usage.get("usage_share_available"):
        note = note or (
            "尚无按 purpose 的选择计量；下列为当前分流策略（配置快照），非流量占比"
        )
    out: Dict[str, Any] = {
        "available": True,
        "simple_purposes": list(_SIMPLE_PURPOSES),
        "complex_purposes": list(_COMPLEX_PURPOSES),
        "purpose_to_model": mapping,
        "purpose_to_model_source": map_source,
        **usage,
        "usage_share_note": note,
    }
    if map_err and not any((mapping.get(p) or "").strip() for p in purposes):
        out["policy_resolve_error"] = map_err
    elif map_err and filled_from_log:
        out["policy_resolve_note"] = (
            f"best_model_for_purpose 不可用（{map_err}）；"
            f"已用 model_selection_log 回填 {filled_from_log} 个用途→模型"
        )
    return out


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
    routing = _model_routing_policy(window_hours=window_hours)
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

    empty_intercept: Dict[str, Any] = {
        "available": False,
        "reason": "ExecutionStore / knowledge_retrieve 事件不可用",
        "count": None,
        "proxy": None,
    }
    if kb.get("available"):
        # Dedicated count: empty retrieve events in window (same SQL as no_answer rate)
        count = kb.get("empty_retrieve_count")
        if count is None and kb.get("total_queries") is not None:
            try:
                rate = float(kb.get("no_answer_rate_pct") or 0) / 100.0
                count = int(round(int(kb.get("total_queries") or 0) * rate))
            except (TypeError, ValueError):
                count = None
        if count is not None:
            empty_intercept = {
                "available": True,
                "count": int(count),
                "label": "empty_kb_retrieve",
                "note": "窗口内空命中检索次数（syscall_events items=[] / count=0）",
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
        src_m = routing.get("purpose_to_model_source") or ""
        if src_m == "model_selection_log":
            lines.append("> 用途→模型来自 model_selection_log 最近选择（运行时解析不可用时回填）")
            lines.append("")
        elif src_m == "mixed":
            lines.append("> 用途→模型：部分来自运行时解析，空缺由 selection_log 回填")
            lines.append("")
        if routing.get("policy_resolve_note"):
            lines.append(f"> {routing.get('policy_resolve_note')}")
            lines.append("")
        lines.append("| 用途 (purpose) | 选用模型 | 档位 |")
        lines.append("|----------------|----------|------|")
        simple = set(routing.get("simple_purposes") or [])
        complex_ = set(routing.get("complex_purposes") or [])
        for p, m in (routing.get("purpose_to_model") or {}).items():
            tier = "简单/轻量" if p in simple else ("复杂/推理" if p in complex_ else "其他")
            lines.append(f"| `{p}` | `{m or '-'}` | {tier} |")
        lines.append("")
        if routing.get("usage_share_available"):
            total = int(routing.get("selection_total") or 0)
            bucket = routing.get("bucket_share_pct") or {}
            src = str(routing.get("usage_share_source") or "")
            unit = "完成调用" if src == "llm_syscall" else "选择次数"
            lines.append(
                f"### 流量占比（{unit}，窗口 {routing.get('window_hours', report.get('window_hours'))}h，"
                f"合计 {total}）"
            )
            lines.append("")
            lines.append(
                f"- **档位占比**: 简单/轻量 {bucket.get('simple', 0)}% · "
                f"复杂/推理 {bucket.get('complex', 0)}% · 其他 {bucket.get('other', 0)}%"
            )
            lines.append("")
            lines.append(f"| 用途 (purpose) | {unit} | 占比 |")
            lines.append("|----------------|----------|------|")
            counts = routing.get("purpose_counts") or {}
            pcts = routing.get("purpose_share_pct") or {}
            for p, c in counts.items():
                lines.append(f"| `{p}` | {c} | {pcts.get(p, 0)}% |")
            lines.append("")
            evidence = (
                "**真实 LLM 完成调用**" if src == "llm_syscall" else "**真实选择计数**"
            )
            lines.append(
                "说明：简单问题走轻量模型、复杂问题走推理/代码模型；"
                f"上表为{evidence}占比，非编造百分比。"
            )
        else:
            lines.append(
                "说明：简单问题走轻量模型、复杂问题走推理/代码模型——"
                "**流量占比暂无计量**，当前不展示虚假百分比。"
            )
    else:
        lines.append(f"- 分流策略 unavailable（{routing.get('reason', 'n/a')}）")

    lines.extend(["", "## 无效请求 / 空检索", ""])
    if empty.get("available") and empty.get("count") is not None:
        lines.append(
            f"- **空检索拦截次数**: {empty.get('count')} 次"
            f"（{empty.get('note') or empty.get('label') or 'empty_kb_retrieve'}）"
        )
        proxy = empty.get("proxy")
        if proxy and proxy.get("value") is not None:
            lines.append(
                f"- 对应无答案率 `{proxy.get('label')}`: {proxy.get('value')}%"
            )
    else:
        lines.append(f"- 空检索计数 unavailable（{empty.get('reason', 'n/a')}）")

    lines.extend(
        [
            "",
            "## 叙事要点（交付话术）",
            "",
            "1. 客户问「一个月花多少」→ 优先给**调用次数 + 缓存命中率**，避免只甩 token 术语。",
            "2. 有账单记录时展示权威 ¥；仅有单价 env 时标注「估算」。",
            "3. 模型分流讲「简单/复杂策略」；优先 LLM 完成调用 purpose 占比，否则选择日志；无数据不编造。",
            "",
        ]
    )
    return "\n".join(lines)
