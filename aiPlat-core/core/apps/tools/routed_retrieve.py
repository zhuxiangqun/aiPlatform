"""routed_retrieve.py — 意图路由统一检索工具（AnySearch 借鉴 P0-2，2026-08-28）。

包装 sys_routed_retrieve：查询理解驱动路由（code/knowledge/web 三通道），
避免全域盲搜；返回结构化信源标注事实条目。生产调用者：server.py 工具注册表。
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from core.apps.tools.base import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


class RoutedRetrieveTool(BaseTool):
    """意图路由统一检索：代码/知识库/Web 三通道按查询意图分发，返回信源标注事实条目。"""

    def __init__(self):
        super().__init__(ToolMetadata(
            name="routed_retrieve",
            description="意图路由统一检索: 先判定查询意图（代码/内部知识/通用事实），"
                        "自动路由到匹配检索通道（code/knowledge/web），返回结构化事实条目"
                        "（含信源标注）。避免全域盲搜，提升结果信噪比。",
            category="retrieval",
            tags=["retrieval", "route", "search", "agent"],
        ))
        self.input_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索查询词",
                },
                "top_k": {
                    "type": "integer",
                    "default": 8,
                    "minimum": 1,
                    "maximum": 20,
                    "description": "返回结果数量",
                },
                "include_web": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否启用 Web 通道（外部信息感知）；隐私敏感场景可关闭",
                },
            },
            "required": ["query"],
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query", "")).strip()
        if not query:
            return {"success": False, "error": "query 不能为空", "route": None,
                    "results": [], "sources": []}
        top_k = min(int(args.get("top_k", 8)), 20)
        include_web = bool(args.get("include_web", True))
        try:
            from core.harness.syscalls.retrieval import sys_routed_retrieve
            r = await sys_routed_retrieve(query, top_k=top_k, include_web=include_web)
            return {
                "success": True,
                "route": r.get("route"),
                "results": r.get("results") or [],
                "sources": r.get("sources") or [],
                "total": len(r.get("results") or []),
            }
        except Exception as e:
            logger.warning("routed_retrieve failed: %s", str(e)[:200])
            return {"success": False, "error": str(e)[:200], "route": None,
                    "results": [], "sources": []}
