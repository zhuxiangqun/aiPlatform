"""Pipeline P95 延迟检测 — 接入 MetricsCollector。

检测 pipeline 端到端延迟的 P95 值是否超出退化阈值。
"""

from typing import Any, Dict


async def check_pipeline_latency() -> Dict[str, Any]:
    try:
        from core.harness.observability.metrics import metrics_collector
        aggregator = metrics_collector.aggregator

        p95_values = []
        for entry in aggregator._history:
            if entry.get("name") == "pipeline_run_duration_ms":
                p95_values.append(float(entry.get("value", 0)))

        if not p95_values:
            return {"status": "pass", "note": "no pipeline latency data yet"}

        p95 = sorted(p95_values)[int(len(p95_values) * 0.95)]

        if p95 > 60000:
            return {"status": "fail", "pipeline_p95_ms": p95,
                    "threshold_ms": 60000, "note": "P95 > 60s — investigate stage bottlenecks"}
        if p95 > 30000:
            return {"status": "warn", "pipeline_p95_ms": p95,
                    "threshold_ms": 30000, "note": "P95 > 30s — degradation detected"}
        return {"status": "pass", "pipeline_p95_ms": p95}
    except Exception as e:
        return {"status": "warn", "reason": str(e)[:150]}
