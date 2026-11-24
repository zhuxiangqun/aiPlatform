"""知识系统生产 SLO 遥测与达标窗口（F1 / 白皮书 §14；显式 residual）。

职责：租户隔离样本记录、对标默认目标的快照、接线门、达标窗口评估；
  显式 residual：opt-in ``evaluate_slo_alert_candidates`` 有界告警候选。

非目标：不升级 Full unconditional / n24_full_conformance；
不采集 ingest/object-sync/索引重建（默认 deepen 仍冻结）；
不做外部 pager/邮件投递（仅结构化候选回执）。

诚实锁：wiring≠attainment；attainment_ok 须窗口达标 + 非作者批准；
告警不可用时诚实上报 ``slo_alerting_unavailable``；certified 恒 false。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 达标窗口：每指标最少有效样本；测试可覆写
DEFAULT_ATTAINMENT_MIN_SAMPLES = 1

# 为什么：镜像 phase2-slo-target-evidence / 白皮书 §14；本刀只接线 3 个已有源指标
DEFAULT_SLO_TARGETS: Dict[str, Dict[str, Any]] = {
    "action_success_rate": {
        "target": 0.995,
        "op": "gte",
        "unit": "ratio",
        "title": "action 成功率",
    },
    "query_p95_ms": {
        "target": 2000.0,
        "op": "lte",
        "unit": "ms",
        "title": "query p95",
    },
    "citation_coverage": {
        "target": 0.99,
        "op": "gte",
        "unit": "ratio",
        "title": "citation 命中率/覆盖率",
    },
}

_METRIC_IDS = tuple(DEFAULT_SLO_TARGETS.keys())


def _default_slo_db_path() -> str:
    """解析 SLO 样本库路径（尊重 AIPLAT_HOME / 测试隔离）。

    Returns:
        SQLite 文件路径。
    """
    env = os.environ.get("AIPLAT_SLO_TELEMETRY_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_slo_telemetry.sqlite3")
    from core.utils.paths import get_aiplat_data_dir

    return str(Path(get_aiplat_data_dir("data")) / "knowledge_slo_telemetry.sqlite3")


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or _default_slo_db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS slo_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            domain_id TEXT DEFAULT '',
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            ok INTEGER DEFAULT 1,
            source TEXT DEFAULT '',
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_slo_tenant_metric_time "
        "ON slo_samples(tenant_id, metric, created_at)"
    )
    return conn


def record_slo_sample(
    metric: str,
    value: float,
    *,
    tenant_id: str,
    domain_id: str = "",
    source: str = "",
    ok: bool = True,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """写入一条租户隔离 SLO 样本。

    Args:
        metric: 指标 id（action_success_rate / query_p95_ms / citation_coverage）。
        value: 样本值。
        tenant_id: 租户；空则拒绝。
        domain_id: 可选域（如 lock-service）。
        source: 样本来源标签（facade/action/retrieve/manual）。
        ok: 业务是否成功（供成功率衍生）。
        db_path: 可选覆盖库路径。

    Returns:
        写入回执（status=ok|error）。
    """
    tid = str(tenant_id or "").strip()
    mid = str(metric or "").strip()
    if not tid:
        return {"status": "error", "reason": "tenant_id_required"}
    if mid not in DEFAULT_SLO_TARGETS:
        return {
            "status": "error",
            "reason": f"unknown_metric:{mid}",
            "allowed": list(_METRIC_IDS),
        }
    try:
        val = float(value)
    except (TypeError, ValueError):
        return {"status": "error", "reason": "value_not_numeric"}

    now = time.time()
    try:
        conn = _connect(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO slo_samples"
                "(tenant_id, domain_id, metric, value, ok, source, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    tid,
                    str(domain_id or ""),
                    mid,
                    val,
                    1 if ok else 0,
                    str(source or "")[:120],
                    now,
                ),
            )
            conn.commit()
            sample_id = int(cur.lastrowid or 0)
        finally:
            conn.close()
    except Exception as e:
        logger.warning("record_slo_sample failed: %s", e, exc_info=True)
        return {"status": "error", "reason": f"persist_failed:{type(e).__name__}"}

    return {
        "status": "ok",
        "sample_id": sample_id,
        "tenant_id": tid,
        "metric": mid,
        "value": val,
        "created_at": now,
    }


def _samples_for_metric(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    metric: str,
    since: float,
    domain_id: str = "",
) -> List[sqlite3.Row]:
    if domain_id:
        return list(
            conn.execute(
                "SELECT * FROM slo_samples WHERE tenant_id=? AND metric=? "
                "AND created_at>=? AND domain_id=? ORDER BY created_at ASC",
                (tenant_id, metric, since, domain_id),
            ).fetchall()
        )
    return list(
        conn.execute(
            "SELECT * FROM slo_samples WHERE tenant_id=? AND metric=? "
            "AND created_at>=? ORDER BY created_at ASC",
            (tenant_id, metric, since),
        ).fetchall()
    )


def _p95(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95)))
    return float(ordered[idx])


def _meets_target(value: Optional[float], spec: Dict[str, Any]) -> Optional[bool]:
    if value is None:
        return None
    target = float(spec["target"])
    op = str(spec.get("op") or "gte")
    if op == "lte":
        return value <= target
    return value >= target


def _live_query_p95_ms() -> Dict[str, Any]:
    """从 cost_estimator 进程内缓冲读 query p95（无租户列；仅作补充源）。"""
    try:
        from core.harness.knowledge.cost_estimator import get_latency_stats

        stats = get_latency_stats("rag") or {}
        samples = int(stats.get("samples") or 0)
        p95 = stats.get("p95_ms")
        return {
            "value": float(p95) if samples > 0 and p95 is not None else None,
            "samples": samples,
            "source": "cost_estimator.rag",
        }
    except Exception:
        logger.debug("live query p95 unavailable", exc_info=True)
        return {"value": None, "samples": 0, "source": "cost_estimator.rag"}


def _live_action_success_rate(domain_id: str) -> Dict[str, Any]:
    """同步读 ActionStore.action_audit 今日成功率（域可选）。"""
    try:
        from core.harness.infrastructure.action_store import (
            USAGE_SUCCESS_STATUSES,
            default_action_db_path,
        )

        path = default_action_db_path()
        if not os.path.exists(path):
            return {"value": None, "samples": 0, "source": "action_audit"}
        success_list = sorted(USAGE_SUCCESS_STATUSES)
        placeholders = ",".join("?" * len(success_list))
        domain = (domain_id or "").strip()
        conn = sqlite3.connect(path, timeout=5.0)
        try:
            if domain:
                sql = f"""
                SELECT COUNT(*) AS n,
                       SUM(CASE WHEN result_status IN ({placeholders})
                                THEN 1 ELSE 0 END) AS ok_n
                FROM action_audit
                WHERE domain_id = ?
                  AND created_at >= date('now', 'start of day')
                """
                row = conn.execute(sql, (*success_list, domain)).fetchone()
            else:
                sql = f"""
                SELECT COUNT(*) AS n,
                       SUM(CASE WHEN result_status IN ({placeholders})
                                THEN 1 ELSE 0 END) AS ok_n
                FROM action_audit
                WHERE created_at >= date('now', 'start of day')
                """
                row = conn.execute(sql, (*success_list,)).fetchone()
        finally:
            conn.close()
        n = int(row[0] or 0) if row else 0
        ok_n = int(row[1] or 0) if row and row[1] is not None else 0
        if n <= 0:
            return {"value": None, "samples": 0, "source": "action_audit"}
        return {
            "value": float(ok_n) / float(n),
            "samples": n,
            "source": "action_audit",
        }
    except Exception:
        logger.debug("live action success unavailable", exc_info=True)
        return {"value": None, "samples": 0, "source": "action_audit"}


def _live_citation_coverage(tenant_id: str, window_hours: int) -> Dict[str, Any]:
    """从 ExecutionStore.syscall_events 估 citation 覆盖率（与 kb/metrics 同口径）。"""
    try:
        from core.services import get_execution_store

        store = get_execution_store()
        db_path = getattr(store, "db_path", None) or getattr(store, "path", None)
        if not db_path or not os.path.exists(str(db_path)):
            return {"value": None, "samples": 0, "source": "syscall_events"}
        cutoff = time.time() - max(1, int(window_hours)) * 3600
        tid = str(tenant_id or "").strip()
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            where = (
                "kind='knowledge_retrieve' AND created_at > ?"
            )
            params: List[Any] = [cutoff]
            if tid:
                where += " AND COALESCE(tenant_id,'') = ?"
                params.append(tid)
            total = conn.execute(
                f"SELECT COUNT(*) FROM syscall_events WHERE {where}", params
            ).fetchone()[0]
            cited = conn.execute(
                f"SELECT COUNT(*) FROM syscall_events WHERE {where} AND ("
                "COALESCE(result_json,'') LIKE '%\"citations\"%' "
                "OR COALESCE(args_json,'') LIKE '%\"citations\"%' "
                "OR COALESCE(result_json,'') LIKE '%\"source\"%')",
                params,
            ).fetchone()[0]
        finally:
            conn.close()
        total_i = int(total or 0)
        if total_i <= 0:
            return {"value": None, "samples": 0, "source": "syscall_events"}
        return {
            "value": float(int(cited or 0)) / float(total_i),
            "samples": total_i,
            "source": "syscall_events",
        }
    except Exception:
        logger.debug("live citation coverage unavailable", exc_info=True)
        return {"value": None, "samples": 0, "source": "syscall_events"}


def get_slo_snapshot(
    tenant_id: str,
    *,
    domain_id: str = "",
    window_hours: int = 24,
    db_path: Optional[str] = None,
    include_live: bool = True,
) -> Dict[str, Any]:
    """返回目标 + 窗口内样本聚合 + 可选 live 源。

    Args:
        tenant_id: 租户；空则 error。
        domain_id: 可选域过滤（仅样本表）。
        window_hours: 回溯窗口小时。
        db_path: 可选样本库路径。
        include_live: 是否合并 ActionStore/cost_estimator/syscall 补充源。

    Returns:
        snapshot dict（status=ok|error）；含 metrics[*].computed / live / meets_target。
    """
    tid = str(tenant_id or "").strip()
    if not tid:
        return {"status": "error", "reason": "tenant_id_required", "metrics": {}}

    since = time.time() - max(1, int(window_hours)) * 3600
    metrics_out: Dict[str, Any] = {}
    try:
        conn = _connect(db_path)
        try:
            for mid, spec in DEFAULT_SLO_TARGETS.items():
                rows = _samples_for_metric(
                    conn,
                    tenant_id=tid,
                    metric=mid,
                    since=since,
                    domain_id=str(domain_id or ""),
                )
                values = [float(r["value"]) for r in rows]
                if mid == "action_success_rate" and rows:
                    oks = [1.0 if int(r["ok"] or 0) else 0.0 for r in rows]
                    # 为什么：成功率用 ok 标志聚合，避免误把延迟当成功率写入
                    computed = sum(oks) / len(oks) if oks else None
                elif mid == "query_p95_ms":
                    computed = _p95(values)
                elif mid == "citation_coverage" and values:
                    computed = sum(values) / len(values)
                else:
                    computed = (sum(values) / len(values)) if values else None

                live: Dict[str, Any] = {"value": None, "samples": 0, "source": ""}
                if include_live:
                    if mid == "action_success_rate":
                        live = _live_action_success_rate(domain_id)
                    elif mid == "query_p95_ms":
                        live = _live_query_p95_ms()
                    elif mid == "citation_coverage":
                        live = _live_citation_coverage(tid, window_hours)

                effective = computed
                effective_samples = len(values)
                effective_source = "slo_samples"
                if effective is None and live.get("value") is not None:
                    effective = live["value"]
                    effective_samples = int(live.get("samples") or 0)
                    effective_source = str(live.get("source") or "live")

                metrics_out[mid] = {
                    "title": spec["title"],
                    "target": spec["target"],
                    "op": spec["op"],
                    "unit": spec["unit"],
                    "samples": len(values),
                    "computed": computed,
                    "live": live,
                    "effective": effective,
                    "effective_samples": effective_samples,
                    "effective_source": effective_source,
                    "meets_target": _meets_target(effective, spec),
                }
        finally:
            conn.close()
    except Exception as e:
        logger.warning("get_slo_snapshot failed: %s", e, exc_info=True)
        return {"status": "error", "reason": f"snapshot_failed:{type(e).__name__}"}

    return {
        "status": "ok",
        "tenant_id": tid,
        "domain_id": str(domain_id or ""),
        "window_hours": int(window_hours),
        "targets": {
            k: {"target": v["target"], "op": v["op"], "title": v["title"]}
            for k, v in DEFAULT_SLO_TARGETS.items()
        },
        "metrics": metrics_out,
        "note": "wiring snapshot; not production attainment",
    }


def evaluate_slo_wiring_gate(
    tenant_id: str,
    *,
    domain_id: str = "",
    window_hours: int = 24,
    db_path: Optional[str] = None,
    include_live: bool = True,
) -> Dict[str, Any]:
    """接线门：三指标均有有效样本 → wiring_ok；attainment/certified 恒 false。

    Args:
        tenant_id: 租户。
        domain_id: 可选域。
        window_hours: 窗口。
        db_path: 样本库。
        include_live: 是否计入 live 源。

    Returns:
        gate dict；空样本不得假绿。
    """
    snap = get_slo_snapshot(
        tenant_id,
        domain_id=domain_id,
        window_hours=window_hours,
        db_path=db_path,
        include_live=include_live,
    )
    if snap.get("status") != "ok":
        return {
            "status": snap.get("status") or "error",
            "reason": snap.get("reason") or "snapshot_failed",
            "wiring_ok": False,
            "attainment_ok": False,
            "certified": False,
            "n24_full_conformance": False,
            "issues": ["snapshot_unavailable"],
            "snapshot": snap,
        }

    issues: List[str] = []
    for mid in _METRIC_IDS:
        m = (snap.get("metrics") or {}).get(mid) or {}
        n = int(m.get("effective_samples") or 0)
        if n <= 0 or m.get("effective") is None:
            issues.append(f"no_samples:{mid}")

    wiring_ok = len(issues) == 0
    return {
        "status": "ok",
        "tenant_id": str(tenant_id or "").strip(),
        "domain_id": str(domain_id or ""),
        "wiring_ok": wiring_ok,
        # 为什么：诚实锁——接线≠达标；无生产窗口批准不得置 attainment/certified
        "attainment_ok": False,
        "certified": False,
        "n24_full_conformance": False,
        "issues": issues,
        "snapshot": snap,
        "note": "wiring_ok may pass; attainment/certified always false on wiring gate",
    }


def _load_slo_approval_record(path: Path) -> Dict[str, Any]:
    """读取 SLO 达标窗口批准记录。

    Args:
        path: JSON 路径。

    Returns:
        批准记录 dict；缺文件或坏 JSON 时含 ``error``。
    """
    if not path.is_file():
        return {"error": f"approval_missing:{path}"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"error": f"approval_invalid:{e}"}


def _slo_approval_allows(rec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """非作者批准是否足以开启 attainment_ok（不开启 certified）。

    Args:
        rec: 批准记录对象。

    Returns:
        (是否允许, issues)。
    """
    issues: List[str] = []
    if rec.get("error"):
        return False, [str(rec["error"])]
    status = str(rec.get("status") or "").lower()
    decision = str(rec.get("decision") or "").lower()
    if status != "approved" or decision not in ("approved", "conditional"):
        issues.append("approval_not_approved")
    scope = str(rec.get("scope") or "").lower()
    # 为什么：拒绝复用 Core/Full 批准文件冒充 SLO 达标窗口批准
    if "slo" not in scope and "attainment" not in scope:
        issues.append("approval_scope_not_slo_attainment")
    approvers = list(rec.get("approvers") or [])
    if not approvers:
        issues.append("approvers_required")
    non_author = False
    for a in approvers:
        if isinstance(a, dict) and a.get("is_author") is False:
            non_author = True
        elif isinstance(a, dict) and a.get("is_author") is True:
            continue
        elif isinstance(a, str) and "author" not in a.lower():
            non_author = True
    if len(approvers) >= 2:
        non_author = True
    if rec.get("conflict_waiver"):
        non_author = True
    if approvers and not non_author:
        issues.append("non_author_approver_required")
    if not str(rec.get("effective_date") or "").strip():
        issues.append("effective_date_required")
    return not issues, issues


def evaluate_slo_attainment_window(
    tenant_id: str,
    *,
    domain_id: str = "",
    window_hours: int = 24,
    db_path: Optional[str] = None,
    include_live: bool = True,
    min_samples: int = DEFAULT_ATTAINMENT_MIN_SAMPLES,
    approval_record_path: Optional[str] = None,
) -> Dict[str, Any]:
    """生产达标窗口评估：窗口内三指标达标 + 非作者批准 → attainment_ok。

    Args:
        tenant_id: 租户。
        domain_id: 可选域。
        window_hours: 回溯窗口小时。
        db_path: 样本库。
        include_live: 是否计入 live 源。
        min_samples: 每指标最少有效样本；不足则窗口未达标。
        approval_record_path: SLO 达标窗口批准 JSON；缺省则 attainment_ok 恒假。

    Returns:
        gate dict。``certified`` / ``n24_full_conformance`` 恒 false（不清除 Full conditional）。
    """
    wiring = evaluate_slo_wiring_gate(
        tenant_id,
        domain_id=domain_id,
        window_hours=window_hours,
        db_path=db_path,
        include_live=include_live,
    )
    snap = wiring.get("snapshot") or {}
    issues: List[str] = list(wiring.get("issues") or [])
    metric_issues: List[str] = []
    min_n = max(1, int(min_samples))

    window_meets = True
    if snap.get("status") != "ok":
        window_meets = False
        if "snapshot_unavailable" not in issues:
            issues.append("snapshot_unavailable")
    else:
        for mid in _METRIC_IDS:
            m = (snap.get("metrics") or {}).get(mid) or {}
            n = int(m.get("effective_samples") or 0)
            if n < min_n:
                metric_issues.append(f"insufficient_samples:{mid}:{n}<{min_n}")
                window_meets = False
                continue
            meets = m.get("meets_target")
            if meets is not True:
                metric_issues.append(f"misses_target:{mid}")
                window_meets = False

    issues.extend(metric_issues)

    approval_issues: List[str] = []
    approval_ok = False
    approval_rec: Dict[str, Any] = {}
    if not approval_record_path:
        approval_issues.append("approval_record_path_required")
    else:
        approval_rec = _load_slo_approval_record(Path(approval_record_path))
        approval_ok, a_issues = _slo_approval_allows(approval_rec)
        approval_issues.extend(a_issues)

    # 为什么：达标徽章仅窗口+批准；绝不自动 certified / Full unconditional
    attainment_ok = bool(
        wiring.get("wiring_ok") and window_meets and approval_ok
    )

    status = "ok"
    if wiring.get("status") not in (None, "ok"):
        status = str(wiring.get("status") or "error")

    return {
        "status": status,
        "tenant_id": str(tenant_id or "").strip(),
        "domain_id": str(domain_id or ""),
        "window_hours": int(window_hours),
        "min_samples": min_n,
        "wiring_ok": bool(wiring.get("wiring_ok")),
        "window_meets_targets": bool(window_meets and wiring.get("wiring_ok")),
        "approval_ok": approval_ok,
        "attainment_ok": attainment_ok,
        "certified": False,
        "n24_full_conformance": False,
        "issues": issues + approval_issues,
        "approval_record_path": approval_record_path,
        "approval_record_id": approval_rec.get("record_id") if approval_ok else None,
        "snapshot": snap,
        "note": (
            "attainment_ok requires window_meets_targets + non-author SLO approval; "
            "certified/n24_full_conformance always false; Full remains conditional"
        ),
    }


def evaluate_slo_alert_candidates(
    tenant_id: str,
    *,
    domain_id: str = "",
    window_hours: int = 24,
    db_path: Optional[str] = None,
    include_live: bool = True,
) -> Dict[str, Any]:
    """SLO residual：从快照生成告警候选（非投递、非 certified）。

    指标未达标或无有效样本时产出候选；默认关闭
    （无 ``AIPLAT_KNOWLEDGE_SLO_ALERT=1`` → ``slo_alerting_unavailable``）。
    即使有候选，``certified`` / ``n24_full_conformance`` / ``attainment_ok`` 仍恒 false。

    Args:
        tenant_id: 租户。
        domain_id: 可选域。
        window_hours: 回溯窗口小时。
        db_path: 样本库。
        include_live: 是否计入 live 源。
    """
    tid = str(tenant_id or "").strip()
    base = {
        "tenant_id": tid,
        "domain_id": str(domain_id or ""),
        "window_hours": int(window_hours),
        "alerts": [],
        "alert_count": 0,
        "attainment_ok": False,
        "certified": False,
        "n24_full_conformance": False,
        "slo_telemetry_freeze": True,
        "accuracy_claim": False,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}

    # 为什么：默认关闭告警候选，避免 CI/本地把接线快照当生产告警投递
    if os.environ.get("AIPLAT_KNOWLEDGE_SLO_ALERT", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return {
            **base,
            "status": "slo_alerting_unavailable",
            "via": "env_disabled",
            "note": "set AIPLAT_KNOWLEDGE_SLO_ALERT=1 to enable alert candidates",
        }

    snap = get_slo_snapshot(
        tid,
        domain_id=domain_id,
        window_hours=window_hours,
        db_path=db_path,
        include_live=include_live,
    )
    if snap.get("status") != "ok":
        return {
            **base,
            "status": "slo_alerting_unavailable",
            "via": "snapshot_unavailable",
            "snapshot": snap,
            "note": "snapshot unavailable; not alert delivery / not certified",
        }

    alerts: List[Dict[str, Any]] = []
    for mid in _METRIC_IDS:
        m = (snap.get("metrics") or {}).get(mid) or {}
        n = int(m.get("effective_samples") or 0)
        meets = m.get("meets_target")
        if n <= 0 or m.get("effective") is None:
            alerts.append(
                {
                    "metric": mid,
                    "severity": "no_samples",
                    "effective_samples": n,
                    "computed": m.get("computed"),
                    "target": (snap.get("targets") or {}).get(mid),
                }
            )
        elif meets is not True:
            alerts.append(
                {
                    "metric": mid,
                    "severity": "misses_target",
                    "effective_samples": n,
                    "computed": m.get("computed"),
                    "meets_target": meets,
                    "target": (snap.get("targets") or {}).get(mid),
                }
            )

    return {
        **base,
        "status": "ok",
        "via": "opt_in",
        "alerts": alerts,
        "alert_count": len(alerts),
        "snapshot": snap,
        "note": (
            "alert candidates only (no pager/email delivery); "
            "not attainment_ok / not certified / Full remains conditional"
        ),
    }


def run_slo_alert_suite(*, db_path: Optional[str] = None) -> Dict[str, Any]:
    """SLO alerting residual 套件（certified 恒 false）。

    Args:
        db_path: 可选临时库。
    """
    import tempfile

    tmp: Optional[tempfile.TemporaryDirectory] = None
    path = db_path
    if not path:
        tmp = tempfile.TemporaryDirectory(prefix="slo-alert-")
        path = str(Path(tmp.name) / "slo.db")

    prev = os.environ.get("AIPLAT_KNOWLEDGE_SLO_ALERT")
    os.environ.pop("AIPLAT_KNOWLEDGE_SLO_ALERT", None)
    cases: List[Dict[str, Any]] = []
    try:
        # 为什么：action_success_rate 按 ok 标志聚合；ok=False 才能造 misses_target
        record_slo_sample(
            "action_success_rate",
            0.0,
            tenant_id="slo-alert-t",
            ok=False,
            db_path=path,
        )
        record_slo_sample(
            "query_p95_ms",
            50.0,
            tenant_id="slo-alert-t",
            ok=True,
            db_path=path,
        )
        record_slo_sample(
            "citation_coverage",
            1.0,
            tenant_id="slo-alert-t",
            ok=True,
            db_path=path,
        )

        unavail = evaluate_slo_alert_candidates(
            "slo-alert-t", db_path=path, include_live=False
        )
        cases.append(
            {
                "id": "slo_alert_unavailable",
                "ok": unavail.get("status") == "slo_alerting_unavailable"
                and unavail.get("certified") is False
                and unavail.get("attainment_ok") is False,
            }
        )

        os.environ["AIPLAT_KNOWLEDGE_SLO_ALERT"] = "1"
        fired = evaluate_slo_alert_candidates(
            "slo-alert-t", db_path=path, include_live=False
        )
        alerts = fired.get("alerts") or []
        has_miss = any(
            a.get("metric") == "action_success_rate"
            and a.get("severity") == "misses_target"
            for a in alerts
            if isinstance(a, dict)
        )
        cases.append(
            {
                "id": "slo_alert_opt_in",
                "ok": fired.get("status") == "ok"
                and has_miss
                and int(fired.get("alert_count") or 0) >= 1
                and fired.get("certified") is False
                and fired.get("n24_full_conformance") is False
                and fired.get("attainment_ok") is False,
            }
        )

        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": fired.get("certified") is False
                and fired.get("slo_telemetry_freeze") is True,
            }
        )
    finally:
        if prev is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_SLO_ALERT", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_SLO_ALERT"] = prev
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(cases) and len(cases) == 3,
        "passed": passed,
        "total": len(cases),
        "cases": cases,
        "certified": False,
        "n24_full_conformance": False,
        "attainment_ok": False,
        "slo_telemetry_freeze": True,
        "note": "SLO alert residual suite; not certified / not Full unconditional",
    }


def evaluate_slo_alert_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """SLO alerting residual 门槛门；certified 恒 false。

    Args:
        suite: ``run_slo_alert_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_slo_alert_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n24_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("attainment_ok") is True:
        issues.append("honesty_attainment_on_alert_forbidden")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in ("slo_alert_unavailable", "slo_alert_opt_in", "honesty_certified_false"):
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n24_full_conformance": False,
        "attainment_ok": False,
        "slo_telemetry_freeze": True,
        "note": "SLO alert residual gate; not certified",
    }


__all__ = [
    "DEFAULT_SLO_TARGETS",
    "DEFAULT_ATTAINMENT_MIN_SAMPLES",
    "record_slo_sample",
    "get_slo_snapshot",
    "evaluate_slo_wiring_gate",
    "evaluate_slo_attainment_window",
    "evaluate_slo_alert_candidates",
    "run_slo_alert_suite",
    "evaluate_slo_alert_gate",
]
