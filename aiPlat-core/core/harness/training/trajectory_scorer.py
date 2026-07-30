"""

TrajectoryScorer — 多维 Agent 执行轨迹质量评分器 (OpenThoughts-Agent aligned).



四维评分:

  complexity (0.3) — 工具调用次数、分支/回退复杂度

  success_rate (0.3) — 子任务成功率

  trajectory_length (0.2) — 执行轮次（更多轮次=更高学习价值，OpenThoughts 发现）

  diversity (0.2) — 与已有数据集的差异化程度



批量查询 — score_batch(run_ids) 一次 DB 往返完成所有评分，避免同步 I/O 阻塞。

"""

from __future__ import annotations



import asyncio

import hashlib

import logging

from typing import Any, Dict, List, Optional



logger = logging.getLogger(__name__)





class TrajectoryScorer:

    """多维 Agent 执行轨迹质量评分器。



    用法:

        scorer = TrajectoryScorer()

        scores = await scorer.score_batch(["run-001", "run-002", ...])

        # scores = {"run-001": 0.85, "run-002": 0.32, ...}

    """



    def __init__(self, *, seed: int = 42):

        self._seed = seed

        self._seen_hashes: set = set()  # 去重用



    # ── Public API ──



    async def score_batch(self, run_ids: List[str]) -> Dict[str, float]:

        """批量评分 — 一次 DB 往返完成所有维度的计算。"""

        if not run_ids:

            return {}



        store = await self._ensure_store()

        scores: Dict[str, float] = {}



        try:

            events_by_run = await self._batch_get_events(store, run_ids)

        except Exception:

            logger.debug("Batch event query failed, falling back to per-run", exc_info=True)

            events_by_run = {}



        for run_id in run_ids:

            events = events_by_run.get(run_id, [])

            if not events:

                try:

                    events = await self._get_events(store, run_id)

                except Exception:

                    continue



            c = self._complexity_score(events)

            s = self._success_rate(events)

            l = self._length_score(events)

            d = self._diversity_score(events)



            score = c * 0.30 + s * 0.30 + l * 0.20 + d * 0.20

            scores[run_id] = round(score, 4)



        return scores



    # ── Dimension scores ──



    def _complexity_score(self, events: list) -> float:

        """工具调用次数 + 操作多样性。>10 次调用的轨迹得满分。"""

        tool_count = sum(1 for e in events if self._is_tool_call(e))

        unique_tools = len(set(

            e.get("name", e.get("tool_name", ""))

            for e in events if self._is_tool_call(e) and e.get("name")

        ))

        return min((tool_count * 0.07 + unique_tools * 0.1), 1.0)



    def _success_rate(self, events: list) -> float:

        """事件中标记为成功 vs 失败的比例。"""

        statuses = [

            str(e.get("status", "")).lower()

            for e in events if e.get("status")

        ]

        if not statuses:

            return 0.5  # 无状态标记 → 中性

        success = sum(1 for s in statuses if s in ("success", "completed", "ok"))

        return success / len(statuses)



    def _length_score(self, events: list) -> float:

        """执行轮次越长，学习价值越高 (OpenThoughts 发现)。

        >3 轮 → 0.5, >6 轮 → 1.0。"""

        rounds = len(events)

        return min(rounds / 8, 1.0)



    def _diversity_score(self, events: list) -> float:

        """基于事件序列哈希的去重检测。与已有轨迹相似则降分。"""

        key = hashlib.md5(

            "|".join(

                str(e.get("name", e.get("kind", "")))

                for e in events[:20]

            ).encode()

        ).hexdigest()[:12]

        if key in self._seen_hashes:

            return 0.1  # 接近重复

        self._seen_hashes.add(key)

        if len(self._seen_hashes) > 10000:

            self._seen_hashes = set(list(self._seen_hashes)[-5000:])

        return 1.0  # 新轨迹



    # ── Learnability Filter (Paper: Data Recipes — teacher ≠ student fit) ──



    async def is_learnable(self, run_id: str, student_model: str,

                           max_steps: int = 5) -> bool:

        """检查轨迹是否适合学生模型学习（可模仿性过滤）。



        用学生模型预测前 N 步的 Action，与教师轨迹对比。

        如果前 max_steps 步中有 >= 2 步不一致 → 该轨迹对学生太难，丢弃。

        """

        try:

            store = await self._ensure_store()

            events = await self._get_events(store, run_id)

            if not events or len(events) < 3:

                return True  # 无法获取足够事件时默认保留，避免误删



            from core.harness.syscalls.llm import sys_llm_generate

            mismatch_count = 0

            for step in events[:max_steps]:

                action_name = str(step.get("name", step.get("tool_name", "")))

                if not action_name:

                    continue

                try:

                    resp = await sys_llm_generate(

                        None,

                        [{"role": "user", "content": f"Predict next action for: {str(step.get('args', ''))[:200]}"}],

                        model_name=student_model,

                        temperature=0.0,

                        max_tokens=50,

                    )

                    predicted = (getattr(resp, "content", "") or "").strip()

                    if action_name not in predicted:

                        mismatch_count += 1

                        if mismatch_count >= 2:

                            return False

                except Exception:

                    logging.getLogger(__name__).debug('is_learnable failed', exc_info=True)
            return True

        except Exception:

            logger.debug("is_learnable check skipped for %s", run_id, exc_info=True)

            return True  # 无法验证时默认保留，避免误删



    # ── Helpers ──



    @staticmethod

    def _is_tool_call(e: dict) -> bool:

        return str(e.get("kind", "")).lower() == "tool"



    async def _ensure_store(self):

        from core.services.execution_store import get_execution_store

        return get_execution_store()



    async def _batch_get_events(self, store, run_ids: List[str]) -> Dict[str, list]:

        """Try batch query; fall back to per-run if not supported."""

        if hasattr(store, "batch_get_syscall_events"):

            return await store.batch_get_syscall_events(run_ids)

        # Fallback: per-run queries

        results = {}

        for rid in run_ids:

            try:

                results[rid] = await self._get_events(store, rid)

            except Exception:

                results[rid] = []

        return results



    async def _get_events(self, store, run_id: str) -> list:

        if hasattr(store, "get_syscall_events"):

            return await store.get_syscall_events(run_id)

        return []

