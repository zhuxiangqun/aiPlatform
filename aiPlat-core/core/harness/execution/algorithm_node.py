"""
Deterministic Algorithm Nodes — no-LLM, guaranteed-correct computation stages.

Algorithm nodes are the counterpart to LLM-based agent stages. They execute
deterministic Python functions — same input always produces same output.
Used for computations that must be auditable, reproducible, and correct:
  - MRP net demand calculations
  - Inventory offset / stock reconciliation
  - Quantity / price validation
  - BOM expansion
  - Currency conversion

Architecture:
  AlgorithmRegistry holds named functions.
  node_config.function_name selects the function.
  node_config.function_params provides arguments.
  node_config takes upstream artifact values via {{stage_key}} Jinja2 resolution.

callers:
  - pipeline_engine._exec_stage (node_type == 'algorithm')
  - OntologyScene (future: referenced by scene models)
"""

from __future__ import annotations

import json as _json
import logging
import math
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Algorithm Registry
# ══════════════════════════════════════════════════════════════

_ALGORITHM_REGISTRY: Dict[str, Callable] = {}


def register_algorithm(name: str, func: Callable) -> None:
    u"""Register a deterministic algorithm function."""
    _ALGORITHM_REGISTRY[name] = func


def get_algorithm(name: str) -> Optional[Callable]:
    u"""Get a registered algorithm by name."""
    return _ALGORITHM_REGISTRY.get(name)


def list_algorithms() -> List[Dict[str, Any]]:
    u"""List all registered algorithms with metadata."""
    return [
        {
            "name": name,
            "doc": (func.__doc__ or "").strip()[:200],
            "arg_count": func.__code__.co_argcount,
        }
        for name, func in _ALGORITHM_REGISTRY.items()
    ]


def execute_algorithm(
    function_name: str,
    params: Dict[str, Any],
    upstream_artifacts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    u"""Execute a registered deterministic algorithm.

    Args:
        function_name: name in the algorithm registry.
        params: parameters from node_config.function_params.
        upstream_artifacts: all upstream stage outputs keyed by artifact name.

    返回:
        {"result": ..., "success": True, "execution_time_ms": ...}
        或 {"success": False, "error": "...", "function_name": ...}

    边界:
      - 确定性——相同输入严格相同输出。不依赖外部状态。
      - 不记录副作用——调用者负责将结果持久化到 Pipeline state 或 A-Box。
      - function_name 必须在 ALGORITHM_REGISTRY 中注册，否则直接失败。
    退路:
      - 函数未注册 → 返回 available functions 列表
      - 需要 LLM 判断 → 使用 agent 节点类型而非 algorithm
    """
    import time as _time

    func = get_algorithm(function_name)
    if func is None:
        return {
            "success": False,
            "error": f"Algorithm '{function_name}' not registered. Available: {list(_ALGORITHM_REGISTRY.keys())}",
            "function_name": function_name,
        }

    start = _time.perf_counter()
    try:
        # Merge upstream artifacts into params for convenience
        merged = dict(params or {})
        if upstream_artifacts:
            merged["_upstream"] = upstream_artifacts

        result = func(**merged)
        elapsed_ms = round((_time.perf_counter() - start) * 1000, 2)

        return {
            "result": result,
            "success": True,
            "execution_time_ms": elapsed_ms,
            "function_name": function_name,
            "deterministic": True,
        }
    except Exception as e:
        elapsed_ms = round((_time.perf_counter() - start) * 1000, 2)
        logger.warning("Algorithm '%s' failed: %s", function_name, str(e)[:200])
        return {
            "success": False,
            "error": str(e),
            "function_name": function_name,
            "execution_time_ms": elapsed_ms,
        }


# ══════════════════════════════════════════════════════════════
# Built-in Algorithms
# ══════════════════════════════════════════════════════════════

def mrp_net_demand(
    gross_demand: float = 0,
    on_hand_inventory: float = 0,
    scheduled_receipts: float = 0,
    safety_stock: float = 0,
    **kwargs,
) -> Dict[str, Any]:
    u"""MRP net demand calculation (deterministic).

    net_requirement = max(0, gross_demand - on_hand_inventory
                          - scheduled_receipts + safety_stock)

    Args:
        gross_demand: total demand for the period.
        on_hand_inventory: current available stock.
        scheduled_receipts: incoming orders already placed.
        safety_stock: minimum inventory buffer.

    Returns:
        {net_requirement, projected_on_hand, gross_demand, ...}
    """
    projected = on_hand_inventory + scheduled_receipts - gross_demand
    net = max(0.0, gross_demand - on_hand_inventory - scheduled_receipts + safety_stock)
    return {
        "gross_demand": gross_demand,
        "on_hand_inventory": on_hand_inventory,
        "scheduled_receipts": scheduled_receipts,
        "safety_stock": safety_stock,
        "projected_on_hand": round(projected, 2),
        "net_requirement": round(net, 2),
        "needs_planned_order": net > 0,
        "planned_order_quantity": round(net, 0) if net > 0 else 0,
    }


mrp_net_demand.__tool_contract__ = {
    "name": "mrp_net_demand",
    "action": "compute",
    "side_effect": "none",
    "not_for": "gross_demand 为零或负值时输出无意义；safety_stock 不应超过 gross_demand",
    "failure_mode": "invalid_input",
    "fallback": "当不确定时，projected_on_hand 可作为参考值",
    "param_draft": {
        "gross_demand": "总需求量 (infer from upstream order quantity)",
        "on_hand_inventory": "当前库存量 (infer from inventory data)",
        "scheduled_receipts": "在途订单量 (default: 0 if unknown)",
        "safety_stock": "安全库存量 (default: 0 if not specified)",
    },
}


def inventory_offset(
    items: Optional[List[Dict[str, Any]]] = None,
    inventory: Optional[Dict[str, float]] = None,
    **kwargs,
) -> Dict[str, Any]:
    u"""Offset demand items against available inventory (deterministic).

    Items are consumed FIFO against available stock. Returns allocated
    quantities and remaining shortages per item.

    Args:
        items: list of dicts with {"id": str, "quantity": float}.
        inventory: dict of {"id": available_quantity}.

    Returns:
        {allocated: [{id, requested, allocated, shortfall}], summary: {...}}
    """
    items = items or []
    inventory = inventory or {}
    alloc = []
    total_requested = 0.0
    total_allocated = 0.0
    total_shortfall = 0.0

    remaining = dict(inventory)
    for idx, item in enumerate(items):
        item_id = item.get("id", str(idx))
        qty = float(item.get("quantity", 0))
        total_requested += qty

        available = remaining.get(item_id, 0.0)
        allocated = min(qty, available)
        shortfall = qty - allocated

        remaining[item_id] = available - allocated
        total_allocated += allocated
        total_shortfall += shortfall

        alloc.append({
            "id": item_id,
            "requested": qty,
            "allocated": round(allocated, 2),
            "shortfall": round(shortfall, 2),
            "fulfilled": shortfall == 0,
        })

    return {
        "allocated": alloc,
        "summary": {
            "total_requested": round(total_requested, 2),
            "total_allocated": round(total_allocated, 2),
            "total_shortfall": round(total_shortfall, 2),
            "fulfillment_rate": round(total_allocated / max(1, total_requested), 3),
            "items_with_shortfall": sum(1 for a in alloc if a["shortfall"] > 0),
        },
    }


inventory_offset.__tool_contract__ = {
    "name": "inventory_offset",
    "action": "compute",
    "side_effect": "none",
    "not_for": "库存数据不完整时结果不可靠；items 为空时 summary 全为零",
    "failure_mode": "invalid_input",
    "fallback": "检查 items_with_shortfall 字段定位缺货项",
}


def validate_quantity(
    value: float = 0,
    min_value: float = 0,
    max_value: Optional[float] = None,
    allow_zero: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    u"""Validate a numeric quantity against constraints (deterministic).

    Returns whether the value is within bounds, with human-readable errors.

    Args:
        value: quantity to validate.
        min_value: minimum allowed (inclusive).
        max_value: maximum allowed (inclusive), None = no upper bound.
        allow_zero: whether zero is a valid value.

    Returns:
        {valid, value, min, max, errors: [str]}
    """
    errors = []
    if not allow_zero and value == 0:
        errors.append(f"Value is zero, but allow_zero=False")
    if value < min_value:
        errors.append(f"Value {value} below minimum {min_value}")
    if max_value is not None and value > max_value:
        errors.append(f"Value {value} exceeds maximum {max_value}")

    return {
        "valid": len(errors) == 0,
        "value": value,
        "min": min_value,
        "max": max_value,
        "errors": errors,
    }


validate_quantity.__tool_contract__ = {
    "name": "validate_quantity",
    "action": "validate",
    "side_effect": "none",
    "not_for": "不能替代业务规则引擎——只做数值范围检查；不验证语义正确性",
    "failure_mode": "constraint_violation",
    "fallback": "查看 errors 字段获取违规详情",
}


def bom_expand(
    root_item: str = "",
    bom: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    quantity: float = 1,
    **kwargs,
) -> Dict[str, Any]:
    u"""Expand a Bill of Materials recursively (deterministic).

    Computes total component quantities needed for a given root item quantity.
    Handles multi-level BOMs via recursion (max depth 20 to prevent loops).

    Args:
        root_item: the top-level item to expand.
        bom: dict of {item_id: [{child_id, quantity_per_unit}]}.
        quantity: number of root items to produce.

    Returns:
        {flat_requirements: {child_id: total_qty}, tree_depth, items_expanded}
    """
    bom = bom or {}
    flat: Dict[str, float] = {}
    expanded = 0

    def _expand(item: str, qty: float, depth: int) -> None:
        nonlocal expanded
        if depth > 20:
            return
        children = bom.get(item, [])
        if not children:
            return
        for child in children:
            child_id = child.get("child_id", child.get("id", ""))
            qpu = float(child.get("quantity_per_unit", child.get("qty", 1)))
            needed = qty * qpu
            flat[child_id] = flat.get(child_id, 0) + needed
            expanded += 1
            _expand(child_id, needed, depth + 1)

    _expand(root_item, quantity, 0)

    return {
        "root_item": root_item,
        "root_quantity": quantity,
        "flat_requirements": {k: round(v, 4) for k, v in flat.items()},
        "items_expanded": expanded,
        "unique_components": len(flat),
    }


bom_expand.__tool_contract__ = {
    "name": "bom_expand",
    "action": "expand",
    "side_effect": "none",
    "not_for": "循环 BOM 会导致无限递归——内置 max_depth=20 保护；不适用于含动态或条件逻辑的 BOM",
    "failure_mode": "recursion_guard",
    "fallback": "检查 items_expanded < 预期值；唯一组件数（unique_components）可用于验证 BOM 完整性",
}


def currency_convert(
    amount: float = 0,
    from_currency: str = "USD",
    to_currency: str = "CNY",
    rates: Optional[Dict[str, float]] = None,
    **kwargs,
) -> Dict[str, Any]:
    u"""Convert currency amounts using provided rates (deterministic).

    No external API call — rates must be provided. This guarantees
    reproducibility: same rates always give same result.

    Args:
        amount: value to convert.
        from_currency: source currency code.
        to_currency: target currency code.
        rates: dict of {currency_code: rate_vs_base}.

    Returns:
        {amount, from, to, converted_amount, rate_used}
    """
    rates = rates or {}
    if from_currency == to_currency:
        return {
            "amount": amount, "from": from_currency, "to": to_currency,
            "converted_amount": amount, "rate_used": 1.0,
        }

    if from_currency not in rates or to_currency not in rates:
        return {
            "success": False,
            "error": f"Missing rate(s): {from_currency}={from_currency in rates}, {to_currency}={to_currency in rates}",
            "available_rates": list(rates.keys()),
        }

    rate = rates[to_currency] / rates[from_currency]
    return {
        "amount": amount,
        "from": from_currency,
        "to": to_currency,
        "converted_amount": round(amount * rate, 2),
        "rate_used": round(rate, 6),
    }


currency_convert.__tool_contract__ = {
    "name": "currency_convert",
    "action": "convert",
    "side_effect": "none",
    "not_for": "不调用外部 API——需要手动提供 rates；不适用于实时汇率或高频交易",
    "failure_mode": "missing_rate",
    "fallback": "如果 from/to 货币相同，直接返回原始金额，不消耗计算",
}


# ══════════════════════════════════════════════════════════════
# Auto-registration
# ══════════════════════════════════════════════════════════════

register_algorithm("mrp_net_demand", mrp_net_demand)
register_algorithm("inventory_offset", inventory_offset)
register_algorithm("validate_quantity", validate_quantity)
register_algorithm("bom_expand", bom_expand)
register_algorithm("currency_convert", currency_convert)
