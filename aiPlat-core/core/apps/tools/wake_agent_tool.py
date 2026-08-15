"""
WakeAgentTool — 零 token 文件变更监控工具

接线 harness/monitoring/wake_agent.py 的 WakeAgent 类 (P0-B3)。
纯确定性 checksum 轮询, 监控阶段无 LLM 调用。提供 status/start/stop 三操作。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from core.apps.tools.base import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


class WakeAgentTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="wake_agent",
            description="零token文件变更监控: 轮询配置路径的checksum, 检测文件/目录变化。"
                        "操作: status(查询状态) / start(开始监控) / stop(停止监控)。"
                        "监控阶段无LLM调用, 纯确定性哈希。",
            category="monitoring",
            tags=["watch", "monitor", "filesystem", "监控"],
        ))
        self.input_schema = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "start", "stop"],
                    "default": "status",
                    "description": "操作类型",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要监控的路径 (start 时使用)",
                },
                "interval": {
                    "type": "integer",
                    "default": 30,
                    "description": "轮询间隔秒数",
                },
            },
            "required": ["action"],
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        action = str(args.get("action", "status"))
        try:
            from core.api.core_facade import wake_agent_start, wake_agent_status, wake_agent_stop
            if action == "start":
                result = await wake_agent_start(paths=args.get("paths"))
            elif action == "stop":
                result = await wake_agent_stop()
            else:
                result = wake_agent_status()
            return {"success": True, **result}
        except Exception as e:
            logger.warning("WakeAgent action %s failed: %s", action, e)
            return {"success": False, "error": str(e)[:300]}
