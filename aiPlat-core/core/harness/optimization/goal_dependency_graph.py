"""
GoalDependencyGraph — 多步骤目标依赖规划 (Phase 39).

对分解出的子目标建立依赖图并确定执行顺序。
复用 PipelineEngine._compute_dependency_layers() 的拓扑排序逻辑。

依赖关系来源:
  - LLM 推理: 两个 Goal 之间是否存在数据/知识依赖
  - 本体推理: Goal 的 source_class 是否有领域内前驱关系
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from core.harness.optimization.goal_generator import Goal, GoalType, Priority

logger = logging.getLogger("aiplat.goal_dependency_graph")


@dataclass
class GoalNode:
    goal: Goal
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    layer: int = 0
    completed: bool = False


@dataclass
class ExecutionPlan:
    layers: List[List[Goal]] = field(default_factory=list)
    unsolvable: List[Goal] = field(default_factory=list)
    total_goals: int = 0

    def remaining(self) -> int:
        return self.total_goals - sum(len(l) for l in self.layers) - len(self.unsolvable)


class GoalDependencyGraph:
    """多步骤目标依赖图管理器。

    功能:
      - add_goal: 注册目标节点
      - add_dependency: 添加显式依赖
      - infer_dependencies: LLM 推断隐式依赖关系
      - compute_execution_order: 拓扑排序确定执行层
      - check_blocked / mark_completed: 执行期间的依赖检查
    """

    def __init__(self):
        self._nodes: Dict[str, GoalNode] = {}
        self._current_plan: Optional[ExecutionPlan] = None

    def add_goal(self, goal: Goal) -> None:
        if goal.goal_id not in self._nodes:
            self._nodes[goal.goal_id] = GoalNode(goal=goal)

    def add_dependency(self, goal_id: str, depends_on: str) -> None:
        if not goal_id or not depends_on:
            return
        self._nodes.setdefault(goal_id, GoalNode(
            goal=Goal(
                goal_id=goal_id, title=goal_id, description="",
                goal_type=GoalType.BUSINESS_OBJECTIVE,
                priority=Priority.LOW,
                estimated_impact="", auto_executable=False,
            )
        ))
        self._nodes.setdefault(depends_on, GoalNode(
            goal=Goal(
                goal_id=depends_on, title=depends_on, description="",
                goal_type=GoalType.BUSINESS_OBJECTIVE,
                priority=Priority.LOW,
                estimated_impact="", auto_executable=False,
            )
        ))
        self._nodes[goal_id].dependencies.add(depends_on)
        self._nodes[depends_on].dependents.add(goal_id)

    async def infer_dependencies(self, goals: List[Goal]) -> None:
        """LLM 推断这批子目标之间的执行依赖关系。

        每次推理最多 200 token，temperature=0.2 以提高一致性。
        """
        if len(goals) < 2:
            return

        for g in goals:
            self.add_goal(g)

        try:
            from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
            adapter = create_selected_adapter(best_model_for_purpose("doc_llm"))

            goal_lines = "\n".join(
                f"{i+1}. [{g.goal_id[:12]}] {g.title}" for i, g in enumerate(goals)
            )
            prompt = (
                "以下是一组待执行的子目标。判断它们之间的执行依赖关系 "
                "(如果子目标 A 的输出或产物是子目标 B 执行的前提，则 B 依赖 A)。"
                "只输出 JSON 数组，每个元素含 'dependent' 和 'depends_on' 两个 goal_id。\n\n"
                f"{goal_lines}\n\n"
                "输出格式: [{\"dependent\": \"goal-id-b\", \"depends_on\": \"goal-id-a\"}]"
            )
            raw = await adapter.generate(prompt, temperature=0.2, max_tokens=200)

            import json as _json
            import re as _re
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("\n```", 1)[0] if "```" in text[3:] else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
            m = _re.search(r"\[.*\]", text, _re.DOTALL)
            if m:
                deps = _json.loads(m.group())
                for dep in deps:
                    if isinstance(dep, dict):
                        self.add_dependency(
                            dep.get("dependent", ""),
                            dep.get("depends_on", ""),
                        )
        except Exception as e:
            logger.debug("dependency inference failed: %s", e)

    def compute_execution_order(self) -> ExecutionPlan:
        """拓扑排序 (Kahn 算法) 确定分层执行顺序。

        同一层内的子目标可并行执行。
        """
        if not self._nodes:
            return ExecutionPlan()

        in_degree: Dict[str, int] = {}
        adj: Dict[str, List[str]] = defaultdict(list)
        id_to_goal: Dict[str, Goal] = {}

        for nid, node in self._nodes.items():
            in_degree.setdefault(nid, 0)
            id_to_goal[nid] = node.goal
            for dep in node.dependencies:
                if dep in self._nodes:
                    in_degree[nid] = in_degree.get(nid, 0) + 1
                    adj.setdefault(dep, []).append(nid)

        queue = deque([nid for nid in self._nodes if in_degree.get(nid, 0) == 0])
        layers: List[List[Goal]] = []
        visited: Set[str] = set()

        while queue:
            layer: List[Goal] = []
            for _ in range(len(queue)):
                nid = queue.popleft()
                visited.add(nid)
                layer.append(id_to_goal[nid])
                for neighbor in adj.get(nid, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            if layer:
                for i, goal in enumerate(layer):
                    self._nodes[goal.goal_id].layer = len(layers)
                layers.append(layer)

        unsolvable = [
            id_to_goal[nid] for nid in self._nodes if nid not in visited
        ]

        plan = ExecutionPlan(
            layers=layers,
            unsolvable=unsolvable,
            total_goals=len(self._nodes),
        )
        self._current_plan = plan
        return plan

    def check_blocked(self, goal_id: str) -> Optional[str]:
        """检查某个 goal 的前置依赖是否都已完成。

        返回阻塞它的 goal_id，或 None (可以执行)。
        """
        node = self._nodes.get(goal_id)
        if not node:
            return None
        for dep in node.dependencies:
            dep_node = self._nodes.get(dep)
            if dep_node and not dep_node.completed:
                return dep
        return None

    def mark_completed(self, goal_id: str) -> None:
        node = self._nodes.get(goal_id)
        if node:
            node.completed = True

    def get_next_batch(self, max_count: int = 3) -> List[Goal]:
        """获取下一批可并行执行的子目标。"""
        ready = [
            n.goal for n in self._nodes.values()
            if not n.completed and self.check_blocked(n.goal.goal_id) is None
        ]
        return ready[:max_count]

    def get_blocked_deps(self, goal_id: str) -> List[str]:
        node = self._nodes.get(goal_id)
        if not node:
            return []
        return [
            dep for dep in node.dependencies
            if not (self._nodes.get(dep) and self._nodes[dep].completed)
        ]

    def stats(self) -> Dict[str, Any]:
        completed = sum(1 for n in self._nodes.values() if n.completed)
        return {
            "total_goals": len(self._nodes),
            "completed": completed,
            "blocked": len(self._nodes) - completed,
            "layers": len(self._current_plan.layers) if self._current_plan else 0,
            "unsolvable": len(self._current_plan.unsolvable) if self._current_plan else 0,
        }


_goal_dependency_graph: Optional[GoalDependencyGraph] = None


def get_goal_dependency_graph() -> GoalDependencyGraph:
    global _goal_dependency_graph
    if _goal_dependency_graph is None:
        _goal_dependency_graph = GoalDependencyGraph()
    return _goal_dependency_graph
