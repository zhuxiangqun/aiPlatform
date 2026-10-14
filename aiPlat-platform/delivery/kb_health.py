"""KB health score panel (HYBRID_ENTERPRISE_KB_HEALTH §1–§2).

Phase-1: metrics + stats + score + narrative suggestions.
Phase-2 soft: miss/low-confidence TOP from syscall_events when store available.
Cache hit rate reuses cost_report._cache_stats (no fake ¥ here).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Score formula weights (HYBRID_ENTERPRISE_KB_HEALTH §2)
_W_CITATION = 30.0
_W_NO_ANSWER = 25.0
_W_ERROR = 20.0
_W_REPEAT = 15.0
_W_BONUS = 10.0


def _pct_to_ratio(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # metrics.to_dict uses *_pct in 0–100; tolerate 0–1 ratios
    if v > 1.0:
        return max(0.0, min(1.0, v / 100.0))
    return max(0.0, min(1.0, v))


def kb_health_score(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Compute 0–100 health score from kb/metrics-shaped dict.

    Spec:
      score = round(
        citation * 30 + (1 - no_answer) * 25 + (1 - error) * 20
        + (1 - repeat) * 15 + bonus * 10
      )
      bonus = 1.0 if citation > 0.8 else citation / 0.8
    Missing rates default to neutral 0 (no penalty / no credit).
    """
    citation = _pct_to_ratio(metrics.get("citation_coverage_pct"))
    no_answer = _pct_to_ratio(metrics.get("no_answer_rate_pct"))
    error = _pct_to_ratio(metrics.get("error_correction_rate_pct"))
    repeat = _pct_to_ratio(metrics.get("repeat_question_rate_pct"))

    # Neutral defaults when unavailable: treat as 0 rate / 0 coverage
    c = citation if citation is not None else 0.0
    na = no_answer if no_answer is not None else 0.0
    er = error if error is not None else 0.0
    rp = repeat if repeat is not None else 0.0
    bonus = 1.0 if c > 0.8 else (c / 0.8 if c > 0 else 0.0)

    raw = (
        c * _W_CITATION
        + (1.0 - na) * _W_NO_ANSWER
        + (1.0 - er) * _W_ERROR
        + (1.0 - rp) * _W_REPEAT
        + bonus * _W_BONUS
    )
    score = int(round(max(0.0, min(100.0, raw))))
    if score >= 85:
        label, band = "优秀", "green"
    elif score >= 70:
        label, band = "良好", "blue"
    elif score >= 55:
        label, band = "待改善", "yellow"
    else:
        label, band = "风险", "red"

    return {
        "score": score,
        "label": label,
        "band": band,
        "components": {
            "citation_coverage": c,
            "no_answer_rate": na,
            "error_correction_rate": er,
            "repeat_question_rate": rp,
            "citation_health_bonus": bonus,
        },
        "inputs_available": {
            "citation_coverage_pct": citation is not None,
            "no_answer_rate_pct": no_answer is not None,
            "error_correction_rate_pct": error is not None,
            "repeat_question_rate_pct": repeat is not None,
        },
    }


def _kb_metrics(tenant_id: str = "", hours: int = 168) -> Dict[str, Any]:
    try:
        from kb.metrics import get_kb_metrics

        m = get_kb_metrics(window_hours=hours, tenant_id=tenant_id or "")
        if not isinstance(m, dict):
            return {"available": False}
        out = dict(m)
        out["available"] = True
        return out
    except Exception as e:
        logger.debug("kb_health metrics: %s", e, exc_info=True)
        return {"available": False, "reason": str(e)}


def _kb_sqlite_path(tenant_id: str) -> str:
    """Mirror platform routes._kb_db_path without importing the FastAPI module."""
    import os
    from pathlib import Path

    tid = str(tenant_id or "").strip() or "default"
    home = (
        os.environ.get("AIPLAT_PLATFORM_HOME")
        or os.environ.get("AIPLAT_HOME")
        or str(Path.home() / ".aiplat")
    )
    return str(Path(home).expanduser() / "kb" / "tenants" / tid / "kb.sqlite3")


def _kb_stats(tenant_id: str = "default") -> Dict[str, Any]:
    """Best-effort document counts from platform KB sqlite (no HTTP / no routes import)."""
    import os
    import sqlite3

    tid = tenant_id or "default"
    dbp = _kb_sqlite_path(tid)
    if not os.path.exists(dbp):
        return {
            "available": True,
            "documents": 0,
            "elements": 0,
            "embeddings": 0,
            "collections": 0,
        }
    try:
        conn = sqlite3.connect(dbp)
        try:
            def _count(table: str) -> int:
                try:
                    row = conn.execute(
                        f"SELECT count(*) FROM {table} WHERE tenant_id=?", (tid,)
                    ).fetchone()
                    return int(row[0] or 0) if row else 0
                except sqlite3.Error:
                    return 0

            return {
                "available": True,
                "documents": _count("documents"),
                "elements": _count("kb_elements"),
                "embeddings": _count("embeddings"),
                "collections": _count("collections"),
            }
        finally:
            conn.close()
    except Exception as e:
        logger.debug("kb_health stats: %s", e, exc_info=True)
        return {"available": False, "reason": str(e)}


def _docs_this_week(
    tenant_id: str = "default",
    collection_id: str = "default",
    window_hours: int = 168,
) -> Dict[str, Any]:
    import os
    import sqlite3

    tid = tenant_id or "default"
    cid = collection_id or "default"
    dbp = _kb_sqlite_path(tid)
    if not os.path.exists(dbp):
        return {"available": True, "count": 0, "collection_id": cid}
    try:
        cutoff = time.time() - window_hours * 3600
        conn = sqlite3.connect(dbp)
        try:
            rows = conn.execute(
                """
                SELECT created_at FROM documents
                WHERE tenant_id=? AND collection_id=?
                """,
                (tid, cid),
            ).fetchall()
        finally:
            conn.close()
        n = 0
        for (created,) in rows or []:
            ts = _parse_ts(created)
            if ts is not None and ts >= cutoff:
                n += 1
        return {"available": True, "count": n, "collection_id": cid}
    except Exception as e:
        logger.debug("kb_health docs_this_week: %s", e, exc_info=True)
        return {"available": False, "reason": str(e), "count": None}


def _parse_ts(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        # not a plain epoch — try ISO below
        logger.debug("kb_health _parse_ts: not a float: %s", s[:40])
    try:
        # ISO
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def _extract_question(payload: Any) -> str:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return ""
    if not isinstance(payload, dict):
        return ""
    for key in ("question", "query", "q", "input"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:200]
    args = payload.get("args") or payload.get("arguments")
    if isinstance(args, dict):
        for key in ("question", "query", "input"):
            v = args.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:200]
    return ""


def _payload_score(payload: Any) -> Optional[float]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    for key in ("score", "top_score", "max_score", "confidence"):
        if key in payload:
            try:
                return float(payload[key])
            except (TypeError, ValueError):
                logger.debug("kb_health _payload_score: bad %s=%r", key, payload.get(key))
                continue
    items = payload.get("items") or payload.get("results") or []
    if isinstance(items, list) and items:
        scores = []
        for it in items:
            if isinstance(it, dict) and "score" in it:
                try:
                    scores.append(float(it["score"]))
                except (TypeError, ValueError):
                    logger.debug("kb_health _payload_score: bad item score=%r", it.get("score"))
                    continue
        if scores:
            return max(scores)
    return None


def _miss_and_low_top(
    *,
    window_hours: int = 168,
    limit: int = 5,
    threshold: float = 0.5,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Best-effort TOP lists from ExecutionStore syscall_events."""
    miss_empty = {
        "available": False,
        "items": [],
        "reason": "ExecutionStore / knowledge_retrieve 事件不可用",
        "window_hours": window_hours,
    }
    low_empty = {
        "available": False,
        "items": [],
        "reason": "ExecutionStore / knowledge_retrieve 事件不可用",
        "window_hours": window_hours,
        "threshold": threshold,
    }
    try:
        from core.api.core_facade import get_kernel_runtime

        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if not store:
            try:
                from core.api.core_facade import get_execution_store

                store = get_execution_store()
            except Exception:
                store = None
        if not store or not hasattr(store, "_config"):
            return miss_empty, low_empty
        import sqlite3 as _sq

        cutoff = time.time() - window_hours * 3600
        conn = _sq.connect(store._config.db_path)
        try:
            rows = conn.execute(
                """
                SELECT payload, created_at FROM syscall_events
                WHERE kind='knowledge_retrieve' AND created_at > ?
                ORDER BY created_at DESC
                LIMIT 2000
                """,
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        miss_empty["reason"] = str(e)
        low_empty["reason"] = str(e)
        return miss_empty, low_empty

    miss_counts: Dict[str, Dict[str, Any]] = {}
    low_items: List[Dict[str, Any]] = []
    for payload, created in rows or []:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        q = _extract_question(payload)
        is_miss = '"count":0' in text or '"count": 0' in text
        if is_miss and q:
            slot = miss_counts.get(q) or {"question": q, "count": 0, "last_asked": None}
            slot["count"] += 1
            ts = _parse_ts(created)
            if ts is not None:
                iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                if not slot["last_asked"] or iso > str(slot["last_asked"]):
                    slot["last_asked"] = iso
            miss_counts[q] = slot
        score = _payload_score(payload)
        if score is not None and score < threshold and q:
            low_items.append(
                {
                    "question": q,
                    "score": round(score, 3),
                    "answer_preview": "",
                }
            )

    miss_sorted = sorted(miss_counts.values(), key=lambda x: (-int(x["count"]), x["question"]))[
        :limit
    ]
    # dedupe low by question keeping lowest score
    low_map: Dict[str, Dict[str, Any]] = {}
    for it in low_items:
        prev = low_map.get(it["question"])
        if prev is None or it["score"] < prev["score"]:
            low_map[it["question"]] = it
    low_sorted = sorted(low_map.values(), key=lambda x: x["score"])[:limit]

    return (
        {
            "available": True,
            "items": miss_sorted,
            "window_hours": window_hours,
        },
        {
            "available": True,
            "items": low_sorted,
            "window_hours": window_hours,
            "threshold": threshold,
        },
    )


def _suggestions(
    *,
    score_info: Dict[str, Any],
    metrics: Dict[str, Any],
    miss_top: Dict[str, Any],
) -> List[str]:
    tips: List[str] = []
    items = miss_top.get("items") or []
    if items:
        names = [str(it.get("question") or "").strip() for it in items[:3] if it.get("question")]
        names = [n for n in names if n]
        if names:
            quoted = "」「".join(names)
            tips.append(f"建议补充「{quoted}」相关文档（来自漏召 TOP）")
    na = _pct_to_ratio(metrics.get("no_answer_rate_pct"))
    if na is not None and na > 0.15:
        tips.append("漏召率偏高（>15%），建议检查常见问题是否已入库并调优检索")
    cit = _pct_to_ratio(metrics.get("citation_coverage_pct"))
    if cit is not None and cit < 0.8:
        tips.append("引用覆盖率不足 80%，建议加强回答溯源与资料质量")
    if score_info.get("score", 100) < 55:
        tips.append("健康分处于风险档：优先紧急入库 + 检索重训")
    elif score_info.get("score", 100) < 70:
        tips.append("健康分待改善：补充文档并关注漏召率")
    if not tips:
        tips.append("维持当前入库节奏；关注漏召率与引用覆盖率即可")
    return tips


def build_kb_health_report(
    *,
    tenant_id: str = "default",
    collection_id: str = "default",
    window_hours: int = 168,
    project_id: str = "",
    low_confidence_threshold: float = 0.5,
) -> Dict[str, Any]:
    metrics = _kb_metrics(tenant_id=tenant_id, hours=window_hours)
    stats = _kb_stats(tenant_id=tenant_id)
    docs_week = _docs_this_week(
        tenant_id=tenant_id,
        collection_id=collection_id,
        window_hours=min(window_hours, 168),
    )
    try:
        from delivery.cost_report import _cache_stats

        cache = _cache_stats()
    except Exception as e:
        cache = {"available": False, "reason": str(e)}

    score_info = kb_health_score(metrics if metrics.get("available") else {})
    miss_top, low_top = _miss_and_low_top(
        window_hours=window_hours,
        limit=5,
        threshold=low_confidence_threshold,
    )
    suggestions = _suggestions(score_info=score_info, metrics=metrics, miss_top=miss_top)

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id or "default",
        "project_id": project_id or "",
        "collection_id": collection_id or "default",
        "window_hours": window_hours,
        "health": score_info,
        "metrics": metrics,
        "stats": stats,
        "docs_this_week": docs_week,
        "cache": cache,
        "miss_top": miss_top,
        "low_confidence_top": low_top,
        "suggestions": suggestions,
        "spec": "packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE_KB_HEALTH.md",
    }


def render_kb_health_markdown(report: Dict[str, Any]) -> str:
    h = report.get("health") or {}
    m = report.get("metrics") or {}
    st = report.get("stats") or {}
    week = report.get("docs_this_week") or {}
    cache = report.get("cache") or {}
    miss = report.get("miss_top") or {}
    low = report.get("low_confidence_top") or {}
    tips = report.get("suggestions") or []

    lines: List[str] = [
        "# 交付报告 · 知识库健康分",
        "",
        f"> 生成时间: {report.get('generated_at', '')}  ",
        f"> 租户: `{report.get('tenant_id', '-')}`  "
        f"集合: `{report.get('collection_id', '-')}`  "
        f"窗口: {report.get('window_hours', '')}h",
        "",
        "规格: `HYBRID_ENTERPRISE_KB_HEALTH.md`",
        "",
        f"## 知识库健康分: {h.get('score', 'n/a')}/100（{h.get('label', '-')}）",
        "",
    ]

    lines.append("## 概览")
    lines.append("")
    if m.get("available"):
        lines.append(f"- **总查询数**: {m.get('total_queries', 0)} 次")
        na = m.get("no_answer_rate_pct")
        na_warn = " ⚠️" if isinstance(na, (int, float)) and float(na) > 15 else ""
        lines.append(f"- **漏召率**: {na if na is not None else 'n/a'}%{na_warn}")
        lines.append(f"- **引用覆盖率**: {m.get('citation_coverage_pct', 'n/a')}%")
        lines.append(f"- **纠错率**: {m.get('error_correction_rate_pct', 'n/a')}%")
        lines.append(f"- **重复问题率**: {m.get('repeat_question_rate_pct', 'n/a')}%")
        lines.append(f"- **审批触发率**: {m.get('approval_trigger_rate_pct', 'n/a')}%")
        lines.append(f"- **权限拦截**: {m.get('permission_blocks', 'n/a')}")
        cycles = m.get("gap_repair_cycles")
        if cycles is not None:
            lines.append(f"- **修复周期**: {cycles}")
    else:
        lines.append(f"- metrics unavailable（{m.get('reason', 'n/a')}）")

    if st.get("available"):
        lines.append(f"- **文档总数**: {st.get('documents', 0)} 篇")
    if week.get("available"):
        lines.append(f"- **本周入库**: {week.get('count', 0)} 篇")
    if cache.get("available"):
        rate = cache.get("hit_rate_pct")
        lines.append(
            f"- **缓存命中率**: {rate if rate is not None else 'n/a'}% "
            f"（命中 {cache.get('hits', 0)} / {cache.get('total_requests', 0)}）"
        )
    else:
        lines.append("- **缓存命中率**: unavailable（见成本页 / semantic_cache）")

    lines.extend(["", "## 漏召 TOP5", ""])
    if miss.get("available") and miss.get("items"):
        for i, it in enumerate(miss["items"], 1):
            lines.append(
                f"{i}. 「{it.get('question', '')}」— 未命中 {it.get('count', 0)} 次"
            )
    elif miss.get("available"):
        lines.append("- （窗口内无空结果查询）")
    else:
        lines.append(f"- 待补 / unavailable（{miss.get('reason', '')}）")

    lines.extend(["", "## 低置信 TOP5", ""])
    if low.get("available") and low.get("items"):
        for i, it in enumerate(low["items"], 1):
            lines.append(
                f"{i}. 「{it.get('question', '')}」— 置信度 {it.get('score', 'n/a')}"
            )
    elif low.get("available"):
        lines.append("- （窗口内无低于阈值的命中）")
    else:
        lines.append(f"- 待补 / unavailable（{low.get('reason', '')}）")

    lines.extend(["", "## 建议（指标 → 运营动作）", ""])
    for t in tips:
        lines.append(f"- {t}")
    lines.append("")
    return "\n".join(lines)


def render_kb_health_plain(report: Dict[str, Any]) -> str:
    """Short human summary for Pi `/aiplat-kb-health`."""
    if not report.get("ok"):
        return "知识库健康面板暂不可用"
    h = report.get("health") or {}
    m = report.get("metrics") or {}
    st = report.get("stats") or {}
    week = report.get("docs_this_week") or {}
    tips = report.get("suggestions") or []
    lines = [
        f"知识库健康分: {h.get('score', 'n/a')}/100（{h.get('label', '-')}）",
        (
            f"本周查询 {m.get('total_queries', 'n/a')} 次 | "
            f"文档 {st.get('documents', 'n/a')} 篇 | "
            f"新增 {week.get('count', 'n/a')} 篇"
        ),
        (
            f"漏召率 {m.get('no_answer_rate_pct', 'n/a')}% | "
            f"引用覆盖率 {m.get('citation_coverage_pct', 'n/a')}%"
        ),
        "",
        f"建议: {tips[0] if tips else '维持当前状态'}",
    ]
    return "\n".join(lines)
