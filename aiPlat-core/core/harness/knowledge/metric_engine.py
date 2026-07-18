u"""
Metric Engine — 业务指标体系 (v2.7).

Loads `metrics` from domain YAML, computes business KPIs from
state_history.db + GraphIndex data with threshold evaluation.

measurement = per-instance formula   (e.g., "completed_at - created_at")
aggregation = multi-instance method  (p95, avg, sum, count, none)
"""
from __future__ import annotations

import logging
import os as _os
import re as _re
import sqlite3 as _sqlite3
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("metric_engine")

DB_PATH = _os.path.expanduser("~/.aiplat/state_changes.db")


@dataclass
class MetricDefinition:
    name: str
    label: str
    description: str = ""
    binds_to: str = ""                      # ontology class name
    measurement: str = ""                   # per-instance formula
    aggregation: str = "avg"                # p95 | avg | sum | count | none
    unit: str = ""
    time_scope: str = "sliding_30d"         # sliding_Nd | monthly | quarterly
    fields_required: List[str] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    thresholds: Dict[str, str] = field(default_factory=dict)
    scenario: List[str] = field(default_factory=list)


def load_metrics(domain_yaml_raw: Dict[str, Any]) -> List[MetricDefinition]:
    u"""Load metric definitions from domain YAML raw dict."""
    raw_metrics = domain_yaml_raw.get("metrics", {})
    result = []
    if not raw_metrics or not isinstance(raw_metrics, dict):
        return result

    # Check ontology classes for fields_required validation
    classes = domain_yaml_raw.get("classes", {})
    for name, raw in raw_metrics.items():
        binds_to = raw.get("binds_to", "")
        fields_req = raw.get("fields_required", [])
        if binds_to and fields_req and binds_to in classes:
            cls_fields = {f.get("name", "") for f in classes[binds_to].get("fields", [])}
            missing = [f for f in fields_req if f not in cls_fields]
            if missing:
                logger.warning(
                    "Metric '%s': fields_required %s not found in class '%s' fields",
                    name, missing, binds_to,
                )
        result.append(MetricDefinition(
            name=name,
            label=raw.get("label", name),
            description=raw.get("description", ""),
            binds_to=binds_to,
            measurement=raw.get("measurement", ""),
            aggregation=raw.get("aggregation", "avg"),
            unit=raw.get("unit", ""),
            time_scope=raw.get("time_scope", "sliding_30d"),
            fields_required=fields_req,
            group_by=raw.get("group_by", []),
            thresholds=raw.get("thresholds", {}),
            scenario=raw.get("scenario", []),
        ))
    return result


def compute(
    metric: MetricDefinition,
    domain_id: str,
    *,
    time_window_days: int = 30,
) -> Dict[str, Any]:
    u"""Compute a metric value from state_history.db + GraphIndex."""
    if not _os.path.exists(DB_PATH):
        return {"value": None, "error": "state_changes.db not found"}

    cutoff = _time.time() - (time_window_days * 86400)
    conn = _sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = _sqlite3.Row

    # Get instances of the bound class
    rows = conn.execute(
        "SELECT DISTINCT entity_name FROM state_changes WHERE domain_id = ? AND class_name = ? AND timestamp >= ?",
        (domain_id, metric.binds_to, cutoff),
    ).fetchall()

    values = []
    for row in rows:
        entity_name = row["entity_name"]
        val = _eval_per_instance(entity_name, metric, domain_id, conn)
        if val is not None:
            values.append(val)

    conn.close()

    if not values:
        return {"value": None, "error": f"No instances found for {metric.binds_to}"}

    agg = metric.aggregation
    import statistics
    if agg == "none" or not agg:
        result_val = round(sum(values) / len(values), 2)
    elif agg == "avg":
        result_val = round(sum(values) / len(values), 2)
    elif agg == "sum":
        result_val = round(sum(values), 2)
    elif agg == "count":
        result_val = len(values)
    elif agg == "p95":
        result_val = round(sorted(values)[int(len(values) * 0.95)], 2)
    elif agg == "p50":
        result_val = round(statistics.median(values), 2)
    else:
        result_val = round(sum(values) / len(values), 2)

    threshold_color = _evaluate_thresholds(result_val, metric.thresholds)

    return {
        "metric_name": metric.name,
        "value": result_val,
        "unit": metric.unit,
        "color": threshold_color,
        "instance_count": len(values),
        "time_window_days": time_window_days,
    }


def get_trend(
    metric: MetricDefinition,
    domain_id: str,
    days: int = 30,
) -> List[Dict[str, Any]]:
    u"""Get daily metric values for the last N days."""
    results = []
    for offset in range(days):
        val = compute(metric, domain_id, time_window_days=1)
        day_str = _time.strftime("%Y-%m-%d", _time.gmtime(_time.time() - offset * 86400))
        val["date"] = day_str
        results.append(val)
    return list(reversed(results))


def scorecard(metrics: List[MetricDefinition], domain_id: str) -> List[Dict[str, Any]]:
    u"""Compute all metrics for a domain, returning a scorecard."""
    result = []
    for m in metrics:
        val = compute(m, domain_id)
        result.append(val)
    return result


def _eval_per_instance(
    entity_name: str,
    metric: MetricDefinition,
    domain_id: str,
    conn,
) -> Optional[float]:
    u"""Evaluate measurement formula for a single instance."""
    formula = metric.measurement
    if not formula:
        return None

    # Simple field references: completed_at, created_at are timestamps from state_changes
    # For "completed_at - created_at": extract transition timestamps
    row = conn.execute(
        "SELECT from_state, to_state, timestamp FROM state_changes WHERE domain_id = ? AND entity_name = ? ORDER BY timestamp",
        (domain_id, entity_name),
    ).fetchall()

    if not row:
        return None

    # Build a dict of state→timestamp
    state_ts = {}
    for r in row:
        state_ts[r["to_state"]] = r["timestamp"]

    # Try simple subtraction pattern: "completed_at - created_at"
    m = _re.match(r'^\s*(\w+)\s*-\s*(\w+)\s*$', formula)
    if m:
        field_a = m.group(1)
        field_b = m.group(2)
        ts_a = state_ts.get(field_a)
        ts_b = state_ts.get(field_b)
        if ts_a and ts_b:
            return ts_a - ts_b
        return None

    # Count pattern: "count(condition) / count(*) * 100"
    m = _re.match(r'count\(([^)]+)\)\s*/\s*count\(\*\)\s*\*\s*(\d+)', formula)
    if m:
        condition = m.group(1)
        multiplier = float(m.group(2))
        # Parse condition: "actual_date <= promised_date"
        cond_m = _re.match(r'(\w+)\s*(<=|>=|<|>|==)\s*(\w+)', condition)
        if cond_m:
            field_c, op, field_d = cond_m.groups()
            total = len(row)
            if total == 0:
                return 0
            met = 0
            for r in row:
                val_c = state_ts.get(field_c) or 0
                val_d = state_ts.get(field_d) or 0
                if op == "<=":
                    if val_c <= val_d:
                        met += 1
                elif op == ">=":
                    if val_c >= val_d:
                        met += 1
            return (met / total) * multiplier
        return 0

    # Default: sum pattern "sum(field)"
    m = _re.match(r'sum\((\w+)\)', formula)
    if m:
        field = m.group(1)
        total = sum(r for r in state_ts.values())
        return total

    return None


def _evaluate_thresholds(value: float, thresholds: Dict[str, str]) -> str:
    u"""Evaluate numeric value against threshold rules. Returns: green|yellow|red."""
    if not thresholds:
        return "green"
    for color, rule in thresholds.items():
        try:
            if _eval_threshold_rule(value, rule):
                return color
        except Exception:
            continue
    return "gray"


def _eval_threshold_rule(value: float, rule: str) -> bool:
    u"""Evaluate a single threshold rule like '<= 4' or '> 4 and <= 8'."""
    rule = rule.strip()
    # Handle "and" compound: split and eval each part
    if " and " in rule.lower():
        parts = rule.lower().split(" and ")
        return all(_eval_single_condition(value, p.strip()) for p in parts)
    return _eval_single_condition(value, rule)


def _eval_single_condition(value: float, condition: str) -> bool:
    m = _re.match(r'(>=|<=|>|<|==|!=)\s*([\d.]+)', condition.strip())
    if not m:
        return False
    op, target = m.group(1), float(m.group(2))
    if op == ">=":
        return value >= target
    elif op == "<=":
        return value <= target
    elif op == ">":
        return value > target
    elif op == "<":
        return value < target
    elif op == "==":
        return value == target
    elif op == "!=":
        return value != target
    return False
