"""
MarkingPropagation — 运行时标记传播 (Palantir Security 3D — Marking 维度)

在每次工具调用时检查数据的标记级别，与 Purpose 的 max_marking_level 做三维交集。

设计:
  - 轻量 wrapper，复用 knowledge_markings.py 的 BFS 传播算法
  - 提供运行时快速检查 (non-blocking, best-effort)
  - 标记沿本体关系传播: hasSource, cites, derivesFrom, parentOf, childOf 等

调用者: PolicyGate.check_tool_3d() → 三维权限计算
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Marking Level Constants ─────────────────────────────────────────────

PUBLIC = 1
INTERNAL = 2
CONFIDENTIAL = 3
RESTRICTED = 4

MARKING_LABELS: Dict[int, str] = {
    PUBLIC: "PUBLIC",
    INTERNAL: "INTERNAL",
    CONFIDENTIAL: "CONFIDENTIAL",
    RESTRICTED: "RESTRICTED",
}


# ── Lightweight Runtime Check ──────────────────────────────────────────

def get_entity_max_marking_level(
    entity_uri: str,
    *,
    collection_id: str = "default",
    max_depth: int = 5,
) -> int:
    """获取实体及其关联数据链的**最高**标记级别 (快速检查，best-effort).

    Returns:
        MarkingLevel 数值 (1-4), 或 PUBLIC(1) 表示无限制
    """
    try:
        from core.harness.knowledge.knowledge_markings import (
            resolve_effective_markings,
            load_markings_config,
        )

        config = load_markings_config(collection_id)
        effective, traces = resolve_effective_markings(
            entity_uri, config, [], max_depth=max_depth
        )

        if not effective:
            return PUBLIC

        return max(m.level for m in effective)

    except Exception as e:
        logger.debug("Marking propagation skipped for %s: %s", entity_uri, e)
        return PUBLIC


def check_marking_clearance(
    entity_uri: str,
    max_allowed_level: int,
    *,
    collection_id: str = "default",
) -> Tuple[bool, str]:
    """检查实体标记是否在允许范围内.

    Args:
        entity_uri: 实体 URI
        max_allowed_level: 允许的最高标记级别 (来自 Purpose)
        collection_id: 集合 ID

    Returns:
        (allowed, reason)
    """
    actual_level = get_entity_max_marking_level(entity_uri, collection_id=collection_id)

    if actual_level <= max_allowed_level:
        return True, f"Marking level {MARKING_LABELS.get(actual_level, '?')} ≤ {MARKING_LABELS.get(max_allowed_level, '?')}"

    return False, (
        f"Marking level {MARKING_LABELS.get(actual_level, '?')} ({actual_level}) "
        f"exceeds max allowed {MARKING_LABELS.get(max_allowed_level, '?')} ({max_allowed_level})"
    )


def check_tool_args_markings(
    tool_args: Optional[Dict[str, Any]],
    max_allowed_level: int,
    *,
    collection_id: str = "default",
) -> Tuple[bool, str]:
    """检查工具参数中引用的数据是否在标记允许范围内.

    扫描 tool_args 中的 entity_uri / collection_id / domain_id 等字段.
    """
    if not tool_args or max_allowed_level >= RESTRICTED:
        return True, "no restrictions"

    # 扫描可能包含实体引用的参数
    entity_keys = ["entity_uri", "entity_id", "target_uri", "target_id", "doc_id"]
    for key in entity_keys:
        if key in tool_args and tool_args[key]:
            allowed, reason = check_marking_clearance(
                tool_args[key],
                max_allowed_level,
                collection_id=collection_id,
            )
            if not allowed:
                return False, f"Tool arg '{key}': {reason}"

    return True, "marking check passed"


def inject_marking_context(
    trace_context: Dict[str, Any],
    entity_uri: str = "",
    collection_id: str = "default",
) -> None:
    """将标记上下文注入 trace_context，供 downstream 的 PolicyGate 3D 评估使用.

    在 MemoryManager.build_context() 或 sys_tool_call 前调用.
    """
    try:
        level = get_entity_max_marking_level(entity_uri, collection_id=collection_id)
        trace_context["_marking_level"] = level
        trace_context["_marking_label"] = MARKING_LABELS.get(level, "PUBLIC")
    except Exception:
        trace_context["_marking_level"] = PUBLIC
        trace_context["_marking_label"] = "PUBLIC"
