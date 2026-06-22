"""
aiplat.harness — 低级 Harness 控制 (Level 3)

直接访问 aiPlat 的 ReAct 执行循环。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

import httpx

from .config import Config, get_config


class ReActLoop:
    """低级 ReAct 执行循环控制。

    Usage:
        loop = ReActLoop(model="qwen2.5-coder:7b", max_steps=20)
        loop.on_hook("PreReasoning", my_callback)
        result = loop.run("分析数据")
    """

    def __init__(
        self,
        *,
        model: str = "",
        max_steps: int = 10,
        config: Optional[Config] = None,
    ):
        self._config = config or get_config()
        self._model = model or self._config.default_model
        self._max_steps = max_steps
        self._hooks: Dict[str, List[Callable]] = {}

    def on_hook(self, event: str, callback: Callable):
        """注册 Hook 回调。

        Args:
            event: Hook 事件名 (PreReasoning, PostReasoning, PreAct, PostAct, etc.)
            callback: 回调函数 async def(stage, context) -> None
        """
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)
        return self

    async def run(self, task_description: str) -> Dict[str, Any]:
        """执行任务。

        Args:
            task_description: 任务描述

        Returns:
            {"ok": bool, "output": Any, "run_id": str, "steps": [...]}
        """
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            body = {
                "kind": "agent",
                "target_id": "react_agent",
                "payload": {
                    "task": task_description,
                    "model": self._model,
                    "max_steps": self._max_steps,
                    "hooks": list(self._hooks.keys()),
                },
                "user_id": "sdk-user",
            }
            resp = await client.post(
                f"{self._config.base_url}/api/core/gateway/execute",
                headers=self._config.headers(),
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    def __repr__(self) -> str:
        return f"ReActLoop(model='{self._model}', max_steps={self._max_steps})"
