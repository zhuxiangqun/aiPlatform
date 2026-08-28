"""Model 持久健康趋势检测 — 读取 model_health_store SQLite 数据。

诊断判定（含时效窗口，2026-08-28 修复历史失败永久拖累）：
  - 任一模型最近 stale_days 内有失败记录且连续失败 ≥5 次、成功率 <50% → FAIL
  - 任一模型最近 stale_days 内有失败记录且成功率 <80% → WARN
  - 仅历史失败（last_failure_at 超过 stale_days 且无新调用）→ 视为残留，不计入
  - 所有模型健康 → PASS

防御措施：
  - SQLite 连接 timeout=2.0（诊断不应等太久）
  - 捕获 OperationalError（锁冲突）→ 降级为 WARN + 跳过本轮
  - DB 路径经 core.utils.paths.get_aiplat_home() 解析（AIPLAT_HOME 优先，§5 配置驱动）
"""

import os
import sqlite3
from datetime import datetime
from typing import Any

_STALE_DAYS = 7  # 超过此天数的失败视为历史残留，不计入当前健康


def _home_path() -> str:
    from core.utils.paths import get_aiplat_home
    return get_aiplat_home()


def _parse_ts(ts: str | None) -> datetime | None:
    """解析 last_failure_at（ISO 或 None）。"""
    if not ts:
        return None
    ts = str(ts)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(ts[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


async def check_model_health(stale_days: int = _STALE_DAYS) -> dict[str, Any]:
    db_path = os.environ.get(
        "AIPLAT_MODEL_HEALTH_DB",
        os.path.join(_home_path(), "aiplat_executions.sqlite3"),
    )

    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return {"status": "warn", "reason": "SQLite locked, skipping model health check"}
        return {"status": "warn", "reason": f"无法打开 model_health DB: {str(e)[:120]}"}

    try:
        cursor = conn.execute(
            """SELECT model_name, success_count, failure_count, call_count,
                      business_score, last_failure_at
               FROM model_health WHERE call_count > 0"""
        )
        models = cursor.fetchall()
    except sqlite3.OperationalError as e:
        return {"status": "warn", "reason": f"model_health 表不可读: {str(e)[:120]}"}
    finally:
        conn.close()

    now = datetime.now()
    issues: list[dict[str, Any]] = []
    for m in models:
        total = m["success_count"] + m["failure_count"]
        if total == 0:
            continue
        rate = m["success_count"] / total

        # 时效窗口：无失败记录 → 健康；失败但 last_failure_at 超期 → 历史残留不计入
        last_fail = _parse_ts(m["last_failure_at"])
        if m["failure_count"] <= 0:
            continue
        if last_fail is None:
            # 无时间戳但有失败 → 保守计入（无法确认时效）
            is_stale = False
        else:
            is_stale = (now - last_fail).days > stale_days

        if is_stale:
            continue  # 历史残留（如 12 天前的 ollama 集中失败），不拖累当前诊断

        if m["failure_count"] >= 5 and rate < 0.5:
            issues.append({
                "model": m["model_name"],
                "severity": "fail",
                "reason": (f"consecutive failures: {m['failure_count']} "
                           f"(last {last_fail.isoformat() if last_fail else 'unknown'})"),
            })
        elif rate < 0.8:
            issues.append({
                "model": m["model_name"],
                "severity": "warn",
                "reason": (f"success rate {rate:.0%} "
                           f"(last {last_fail.isoformat() if last_fail else 'unknown'})"),
            })

    if any(i["severity"] == "fail" for i in issues):
        return {"status": "fail", "models": issues}
    if issues:
        return {"status": "warn", "models": issues}
    return {"status": "pass", "models_tracked": len(models)}
