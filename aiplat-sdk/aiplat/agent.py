"""
aiplat.agent — 3 行代码创建并执行 AI Agent。

对齐 Claude Code Agent SDK 的 Level 1 封装。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from .config import Config, get_config

logger = logging.getLogger(__name__)


class Agent:
    """aiPlat Agent — 高级会话级编排器。

    Usage:
        agent = Agent(name="my-analyst", model="qwen2.5-coder:7b")
        agent.bind_skill("data_analysis")
        agent.bind_tool("file_operations")

        # 同步执行
        result = agent.execute("分析销售数据")

        # 流式执行
        async for chunk in agent.stream("生成报告"):
            print(chunk, end="")

        # 多轮对话
        agent.chat("你好")
        reply = agent.chat("刚才说到哪里了？")
    """

    def __init__(
        self,
        *,
        name: str = "",
        model: str = "",
        config: Optional[Config] = None,
        session_id: str = "",   # 共享 Web UI 会话
        run_id: str = "",        # 共享 Pipeline run
    ):
        self._config = config or get_config()
        self._name = name or f"agent-{uuid.uuid4().hex[:8]}"
        self._model = model or self._config.default_model
        self._session_id: str = session_id or f"sdk-{uuid.uuid4().hex[:12]}"
        self._run_id: str = run_id or ""
        self._messages: List[Dict[str, str]] = []
        self._agent_id: Optional[str] = None
        self._created = False
        self._permission_grant_failed = False

    # ── Public API ──────────────────────────────────────────────────────

    def bind_skill(self, skill_name: str):
        """绑定 Skill 到 Agent。

        Args:
            skill_name: Skill 名称 (如 'data_analysis', 'code_generation')
        """
        self._skills.append(skill_name)
        return self

    def bind_tool(self, tool_name: str):
        """绑定 Tool 到 Agent。

        Args:
            tool_name: Tool 名称 (如 'file_operations', 'search')
        """
        self._tools.append(tool_name)
        return self

    def execute(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """同步执行任务。

        Args:
            prompt: 用户输入
            **kwargs: 传递给 Agent 的额外参数 (max_steps, toolset 等)

        Returns:
            {"ok": bool, "output": Any, "run_id": str, ...}
        """
        return asyncio.run(self._execute_async(prompt, **kwargs))

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """流式执行任务 (SSE Token 级输出)。

        Args:
            prompt: 用户输入
            **kwargs: 额外参数

        Yields:
            每个 Token 字符串
        """
        await self._ensure_agent()
        async with httpx.AsyncClient(timeout=self._config.stream_timeout) as client:
            body = {
                "input": {"text": prompt},
                "context": {"tenant_id": self._config.tenant_id, "_run_id": self._run_id},
                "user_id": "sdk-user",
                "session_id": self._session_id,
                "config": {"model": self._model},
                "options": {"stream": "true"},
            }
            body.update(kwargs)

            async with client.stream(
                "POST",
                f"{self._config.base_url}/api/core/workspace/agents/{self._agent_id}/execute",
                headers=self._config.headers(),
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if isinstance(data, dict) and "text" in data:
                                yield data["text"]
                            elif isinstance(data, str):
                                yield data
                        except json.JSONDecodeError:
                            continue

    def chat(self, message: str) -> Dict[str, Any]:
        """多轮对话。

        Args:
            message: 用户消息

        Returns:
            {"ok": bool, "answer": str, ...}
        """
        self._messages.append({"role": "user", "content": message})
        result = self.execute(message, messages=self._messages)
        reply = result.get("output", {}).get("answer", "") if isinstance(result.get("output"), dict) else str(result.get("output", ""))
        if reply:
            self._messages.append({"role": "assistant", "content": reply})
        return result

    def reset(self):
        """重置对话历史。"""
        self._messages = []
        self._session_id = f"sdk-{uuid.uuid4().hex[:12]}"

    # ── Internal ────────────────────────────────────────────────────────

    async def _ensure_agent(self):
        """Create agent via Workspace API if not exists."""
        if self._created:
            return
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            # Create agent
            resp = await client.post(
                f"{self._config.base_url}/api/core/workspace/agents",
                headers=self._config.headers(),
                json={
                    "name": self._name,
                    "description": f"SDK Agent: {self._name}",
                    "agent_type": "base",
                    "config": {"model": self._model},
                    "skills": self._skills,
                    "tools": self._tools,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._agent_id = data.get("id") or data.get("agent_id")
            if not self._agent_id:
                raise RuntimeError(f"Failed to create agent: {data}")
            self._created = True

            # Grant execute permission (best-effort)
            try:
                await client.post(
                    f"{self._config.base_url}/api/core/permissions/grant",
                    headers=self._config.headers(),
                    json={
                        "user_id": "sdk-user",
                        "resource_type": "agent",
                        "resource_id": self._agent_id,
                        "permission": "execute",
                    },
                )
            except Exception:
                logger.warning("Failed to grant execute permission for agent %s", self._agent_id, exc_info=True)
                self._permission_grant_failed = True

    async def _execute_async(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """异步执行核心逻辑。"""
        await self._ensure_agent()
        if self._permission_grant_failed:
            raise PermissionError(
                f"Agent '{self._agent_id}' execute permission was not granted. "
                "Check agent permissions or contact administrator."
            )
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            body = {
                "input": {"text": prompt},
                "context": {"tenant_id": self._config.tenant_id, "_run_id": self._run_id},
                "user_id": "sdk-user",
                "session_id": self._session_id,
                "config": kwargs.pop("config", {"model": self._model}),
            }
            body.update(kwargs)

            resp = await client.post(
                f"{self._config.base_url}/api/core/workspace/agents/{self._agent_id}/execute",
                headers=self._config.headers(),
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    def __repr__(self) -> str:
        status = "created" if self._created else "pending"
        return f"Agent(name='{self._name}', model='{self._model}', skills={self._skills}, status='{status}')"
