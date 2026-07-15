"""FDE Trends — system trends + health history (split from fde.py)."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

import json, time, os

router = APIRouter(tags=["fde-trends"])


@router.get("/trends/system", response_model=dict)
async def fde_system_trends(
    weeks: int = Query(12, ge=4, le=52, description="Weeks of history"),
):
    """System-level trends: atom growth, coverage changes, delivery rates.

    Reads SystemSnapshot entities from knowledge-atom GraphIndex and computes
    week-over-week trends for all key metrics.
    """
    from core.harness.ontology_engine.graph_index import GraphIndex
    from datetime import datetime, timezone, timedelta
    import json as _json_st

    kg = GraphIndex.load("knowledge-atom")
    now = datetime.now(timezone.utc)
    cutoff_ts = int((now - timedelta(weeks=weeks)).timestamp())

    snapshots = []
    for _, n in kg._nodes.items():
        if getattr(n, "class_name", "") != "SystemSnapshot":
            continue
        try:
            ts = int(getattr(n, "source_doc_id", "0"))
            if ts < cutoff_ts:
                continue
            data = _json_st.loads(n.entity_name)
            snapshots.append({"ts": ts, "data": data})
        except Exception:
            continue

    snapshots.sort(key=lambda s: s["ts"])

    # Extract trends
    trends = {}
    metrics = [
        ("configured_domains", "components.domains.count"),
        ("delivery_sessions", "components.delivery.sessions"),
        ("delivery_rate", "components.delivery.delivery_rate"),
        ("atoms", "components.context_bus.layers_ok"),
    ]
    for name, path_str in metrics:
        path = path_str.split(".")
        series = []
        for s in snapshots:
            val = s["data"]
            try:
                for key in path:
                    val = val.get(key, {})
                series.append({"date": datetime.fromtimestamp(s["ts"], tz=timezone.utc).strftime("%Y-%m-%d"), "value": val if isinstance(val, (int, float)) else 0})
            except Exception:
                continue
        if series:
            trends[name] = series[-15:]  # last 15 data points

    return {
        "weeks": weeks,
        "snapshot_count": len(snapshots),
        "trends": trends,
        "latest": snapshots[-1]["data"] if snapshots else None,
    }


@router.get("/health/history", response_model=dict)
async def fde_health_history(
    limit: int = Query(10, ge=1, le=50),
):
    """Last N health check snapshots for comparison."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    import json as _json_hh
    from datetime import datetime, timezone

    kg = GraphIndex.load("knowledge-atom")
    entries = []
    for nid, n in kg._nodes.items():
        if getattr(n, "class_name", "") == "SystemSnapshot" and nid.startswith("snap_"):
            try:
                ts = int(getattr(n, "source_doc_id", "0"))
                data = _json_hh.loads(n.entity_name)
                entries.append({
                    "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                    "status": data.get("status", ""),
                    "domains": data.get("components", {}).get("domains", {}).get("count", 0),
                    "pipeline_ok": data.get("components", {}).get("context_bus", {}).get("layers_ok", 0),
                })
            except Exception:
                continue

    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    entries = entries[:limit]

    return {
        "total_snapshots": sum(1 for n in kg._nodes.values() if getattr(n, "class_name", "") == "SystemSnapshot"),
        "returned": len(entries),
        "history": entries,
    }
