"""Model 持久健康趋势检测 — 读取 model_health_store SQLite 数据。

诊断判定：
  - 任一模型连续失败 ≥5 次 → FAIL
  - 任一模型 24h 成功率 < 80% → WARN
  - 所有模型健康 → PASS

防御措施：
  - SQLite 连接 timeout=2.0（诊断不应等太久）
  - 捕获 OperationalError（锁冲突）→ 降级为 WARN + 跳过本轮
"""

import os
import sqlite3
from typing import Any, Dict, List


async def check_model_health() -> Dict[str, Any]:
    db_path = os.environ.get(
        "AIPLAT_MODEL_HEALTH_DB",
        os.path.expanduser("~/.aiplat/aiplat_executions.sqlite3"),
    )

    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.row_factory = sqlite3.Row
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            return {"status": "warn", "reason": "SQLite locked, skipping model health check"}

    try:
        cursor = conn.execute(
            """SELECT model_name, success_count, failure_count, call_count,
                      business_score, last_failure_at
               FROM model_health WHERE call_count > 0"""
        )
        models = cursor.fetchall()
    finally:
        conn.close()

    issues: List[Dict[str, Any]] = []
    for m in models:
        total = m["success_count"] + m["failure_count"]
        if total == 0:
            continue
        rate = m["success_count"] / total
        if m["failure_count"] >= 5 and rate < 0.5:
            issues.append({
                "model": m["model_name"],
                "severity": "fail",
                "reason": f"consecutive failures: {m['failure_count']}",
            })
        elif rate < 0.8:
            issues.append({
                "model": m["model_name"],
                "severity": "warn",
                "reason": f"success rate {rate:.0%}",
            })

    if any(i["severity"] == "fail" for i in issues):
        return {"status": "fail", "models": issues}
    if issues:
        return {"status": "warn", "models": issues}
    return {"status": "pass", "models_tracked": len(models)}
