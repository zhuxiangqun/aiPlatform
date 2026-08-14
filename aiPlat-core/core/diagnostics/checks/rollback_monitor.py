"""回滚率部署后分析 — 纯 JSONL 读取方案。

读取 deploy_engine 写入的 rollback_events.jsonl（即时持久化），
统计 24h 内版本降级型回滚次数。

数据源优先级：JSONL（唯一数据源）
过滤规则：只统计 event_type="auto_rollback" 且 revision_to < revision_from
排除：HPA 重启、运维手动操作（当前无此数据，按 event_type 区分）

NOTE: V2 需对接 K8s Event API 或 ArgoCD Webhook 获取更精确的部署层回滚信号。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List

_ROLLBACK_LOG = Path.home() / ".aiplat" / "data" / "rollback_events.jsonl"


async def check_rollback_rate() -> Dict[str, Any]:
    if not _ROLLBACK_LOG.exists():
        return {"status": "pass", "rollback_count_24h": 0, "note": "no rollback log yet"}

    cutoff = time.time() - 86400
    events: List[Dict] = []

    try:
        with open(_ROLLBACK_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if ev.get("timestamp", 0) > cutoff:
                        events.append(ev)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception:
        return {"status": "warn", "reason": "failed to read rollback log"}

    # 只统计版本降级型回滚
    rollbacks = [
        e for e in events
        if e.get("event_type") == "auto_rollback"
        and e.get("revision_to", 999) < e.get("revision_from", 0)
    ]

    if len(rollbacks) >= 3:
        return {
            "status": "fail",
            "rollback_count_24h": len(rollbacks),
            "source": "jsonl",
            "note": "≥3 rollbacks in 24h — investigate deployment stability",
        }
    if len(rollbacks) >= 1:
        return {
            "status": "warn",
            "rollback_count_24h": len(rollbacks),
            "source": "jsonl",
        }
    return {"status": "pass", "rollback_count_24h": 0, "source": "jsonl"}
