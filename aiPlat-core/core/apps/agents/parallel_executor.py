"""
Multi-Agent Parallel Executor — Map-Reduce 模式子任务并发执行。

Usage:
    executor = ParallelExecutor(max_concurrency=5)
    results = await executor.map(
        tasks=["分析A", "分析B", "分析C"],
        agent_factory=lambda: Agent(name="analyst", model="qwen2.5-coder:7b"),
    )
    final = await executor.reduce(results, summary_prompt="对比以下分析结果")
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple


class ParallelExecutor:
    """Map-Reduce 并行执行器。

    Map Phase: 并发执行子任务 (asyncio.gather)
    Reduce Phase: 聚合结果 → LLM 生成最终答案

    异常隔离: 单个子任务失败不影响其他 (return_exceptions=True)
    """

    def __init__(self, max_concurrency: int = 5):
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def map(
        self,
        tasks: List[str],
        agent_factory: Callable[[], Any],
        *,
        run_id: str = "",
    ) -> List[Dict[str, Any]]:
        """并发执行多个子任务。

        Args:
            tasks: 任务描述列表
            agent_factory: 创建 Agent 的可调用对象 (每次调用返回新 Agent 实例, 隔离状态)
            run_id: 父 run_id

        Returns:
            每个任务的结果列表 (顺序与输入一致, 失败项包含 error 字段)
        """
        run_id = run_id or f"parallel-{uuid.uuid4().hex[:12]}"
        started_at = time.time()

        async def _run_one(idx: int, task: str) -> Dict[str, Any]:
            """执行单个子任务 (含信号量和异常隔离)。"""
            sub_run_id = f"{run_id}-{idx:03d}"
            async with self._semaphore:
                try:
                    agent = agent_factory()
                    result = agent.execute(task)
                    if isinstance(result, dict):
                        result["_sub_run_id"] = sub_run_id
                        result["_task_index"] = idx
                    return result or {"ok": True, "output": str(result)}
                except Exception as e:
                    return {
                        "ok": False,
                        "error": str(e),
                        "_sub_run_id": sub_run_id,
                        "_task_index": idx,
                    }

        # 并行执行 (return_exceptions=False: 异常已在上方捕获)
        coros = [_run_one(i, t) for i, t in enumerate(tasks)]
        results = await asyncio.gather(*coros)

        elapsed = time.time() - started_at
        return {
            "ok": True,
            "run_id": run_id,
            "elapsed_seconds": round(elapsed, 2),
            "total_tasks": len(tasks),
            "successful": sum(1 for r in results if r.get("ok", False)),
            "failed": sum(1 for r in results if not r.get("ok", False)),
            "results": results,
            "stats": {
                "concurrency": self._max_concurrency,
                "serial_time_estimate": f"~{round(elapsed * self._max_concurrency, 1)}s",
            },
        }

    async def reduce(
        self,
        map_result: Dict[str, Any],
        summary_prompt: str = "",
        *,
        reduce_agent: Any = None,
    ) -> Dict[str, Any]:
        """聚合子任务结果。

        Args:
            map_result: map() 返回的结果
            summary_prompt: 聚合提示 (如 "对比以下分析结果并给出综合结论")
            reduce_agent: 聚合用的 Agent (如不提供, 需作为 agent_factory 的默认 Agent)

        Returns:
            聚合后的最终答案
        """
        results = map_result.get("results", [])
        if not results:
            return {"ok": False, "error": "No map results to reduce"}

        # Build the aggregation prompt
        combined = summary_prompt or "综合分析以下结果并给出结论"
        combined += "\n\n"
        for i, r in enumerate(results):
            if r.get("ok"):
                output = r.get("output", {})
                text = output.get("answer", "") if isinstance(output, dict) else str(output)
                combined += f"## 子任务 {i+1}\n{text[:500]}\n\n"
            else:
                combined += f"## 子任务 {i+1}\n❌ 失败: {r.get('error', 'Unknown')}\n\n"

        agent = reduce_agent
        if not agent:
            from core.apps.agents.materials_chat import MaterialsChatAgent  # noqa: F811
            agent = MaterialsChatAgent()

        reduce_result = agent.execute(combined) if hasattr(agent, 'execute') else {"ok": False, "error": "No reduce agent"}
        reduce_result["_map_stats"] = {
            "total": map_result.get("total_tasks"),
            "successful": map_result.get("successful"),
            "failed": map_result.get("failed"),
            "elapsed": map_result.get("elapsed_seconds"),
        }
        return reduce_result

    async def map_reduce(
        self,
        tasks: List[str],
        agent_factory: Callable[[], Any],
        *,
        summary_prompt: str = "",
        reduce_agent: Any = None,
    ) -> Dict[str, Any]:
        """Map → Reduce 一键执行。

        Args:
            tasks: 子任务列表
            agent_factory: Agent 工厂
            summary_prompt: 聚合提示
            reduce_agent: 聚合 Agent

        Returns:
            最终结果 (含 map 统计信息)
        """
        map_result = await self.map(tasks, agent_factory)
        return await self.reduce(map_result, summary_prompt, reduce_agent=reduce_agent)


# ── Convenience: process in background with progress ─────────────────────

async def parallel_analyze(
    topics: List[str],
    agent_factory: Callable[[], Any],
    *,
    max_concurrency: int = 3,
    on_progress: Optional[Callable[[int, int, str], Any]] = None,
) -> Dict[str, Any]:
    """便捷函数: 并行分析多个主题。

    Args:
        topics: 主题列表
        agent_factory: Agent 工厂
        max_concurrency: 最大并发数
        on_progress: 进度回调 (completed, total, current_topic) -> None

    Returns:
        聚合结果
    """
    executor = ParallelExecutor(max_concurrency=max_concurrency)

    completed = 0
    total = len(topics)

    async def _tracked_factory():
        nonlocal completed
        agent = agent_factory()
        original_execute = agent.execute

        def _tracked_execute(prompt: str, **kwargs):
            result = original_execute(prompt, **kwargs)
            completed += 1
            if on_progress:
                on_progress(completed, total, prompt[:50])
            return result

        agent.execute = _tracked_execute
        return agent

    return await executor.map_reduce(
        topics,
        _tracked_factory,
        summary_prompt=f"对比分析以下 {total} 个主题并给出综合结论",
    )
