"""
PartnerSelector — Agent 协作伙伴选择器 (EvoMap 自组织对齐)

根据 Agent 的专长和能力，自动选择协作伙伴:

  mode="social"       → 偏好"朋友的朋友" (只看社交关系)
  mode="capability"   → 偏好高成功率者 (只看能力)
  mode="complementary" → 偏好专业互补者 (低相似度但相关)

与 EvoMap 实验二对齐: 同一群 Agent 只因看到的可见信息不同，
就会选择不同的伙伴，从而长成不同的网络结构。

调用者: SubagentCoordinator / AgentNetworkPanel
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── PartnerSelector ─────────────────────────────────────────────────────────

class PartnerSelector:
    """协作伙伴选择器.

    使用方式:
        selector = PartnerSelector()
        partners = await selector.select(
            agent_id="agent_1",
            candidates=["agent_2", "agent_3", "agent_4"],
            mode="capability",
            count=3,
        )
    """

    async def select(
        self,
        agent_id: str,
        candidates: List[str],
        *,
        mode: str = "capability",
        count: int = 3,
        social_graph: Optional[Dict[str, List[str]]] = None,
        domain_list: Optional[List[str]] = None,
    ) -> List[str]:
        """选择协作伙伴.

        Args:
            agent_id: 当前 Agent ID
            candidates: 候选 Agent ID 列表
            mode: 选择模式
            count: 选择的伙伴数量
            social_graph: 社交关系图 {agent_id: [friend_ids]} (仅 social 模式需要)
            domain_list: 领域列表 (用于互补性计算)

        Returns:
            选择的伙伴 ID 列表
        """
        if not candidates:
            return []

        if mode == "social":
            return await self._select_social(agent_id, candidates, count, social_graph)
        elif mode == "complementary":
            return await self._select_complementary(agent_id, candidates, count, domain_list)
        else:  # "capability" (default)
            return await self._select_capability(agent_id, candidates, count)

    async def _select_social(
        self,
        agent_id: str,
        candidates: List[str],
        count: int,
        social_graph: Optional[Dict[str, List[str]]],
    ) -> List[str]:
        """社交优先: 偏好"朋友的朋友"."""
        if not social_graph:
            return random.sample(candidates, min(count, len(candidates)))

        friends = set(social_graph.get(agent_id, []))
        friends_of_friends: Dict[str, int] = {}

        for friend in friends:
            for fof in social_graph.get(friend, []):
                if fof != agent_id and fof in candidates:
                    friends_of_friends[fof] = friends_of_friends.get(fof, 0) + 1

        # Sort by mutual friend count
        ranked = sorted(friends_of_friends.items(), key=lambda x: x[1], reverse=True)
        selected = [r[0] for r in ranked[:count]]

        # Fill remaining with random
        remaining = [c for c in candidates if c not in selected]
        selected.extend(random.sample(remaining, min(count - len(selected), len(remaining))))

        return selected[:count]

    async def _select_capability(
        self,
        agent_id: str,
        candidates: List[str],
        count: int,
    ) -> List[str]:
        """能力优先: 按成功率排序."""
        try:
            from core.harness.learning.agent_specialization import AgentSpecialization

            spec = AgentSpecialization()
            ranked: List[Tuple[str, float]] = []

            for cid in candidates:
                vec = await spec.compute(cid, lookback_hours=168)
                total_success = sum(s.success_count for s in vec.domains.values())
                total_actions = max(vec.total_actions, 1)
                score = total_success / total_actions * (1 + len(vec.domains) * 0.1)
                ranked.append((cid, score))

            ranked.sort(key=lambda x: x[1], reverse=True)
            return [r[0] for r in ranked[:count]]

        except Exception as e:
            logger.debug("Capability selection failed, falling back to random: %s", e)
            return random.sample(candidates, min(count, len(candidates)))

    async def _select_complementary(
        self,
        agent_id: str,
        candidates: List[str],
        count: int,
        domain_list: Optional[List[str]],
    ) -> List[str]:
        """互补优先: 选择专业互补的伙伴."""
        try:
            from core.harness.learning.agent_specialization import AgentSpecialization

            spec = AgentSpecialization()
            my_vec = await spec.compute(agent_id, lookback_hours=168)

            ranked: List[Tuple[str, float]] = []
            for cid in candidates:
                c_vec = await spec.compute(cid, lookback_hours=168)
                comp = spec.complementarity_score(my_vec, c_vec, domain_list)
                # Also factor in capability
                c_score = sum(s.success_count for s in c_vec.domains.values()) / max(c_vec.total_actions, 1)
                combined = comp * 0.7 + c_score * 0.3
                ranked.append((cid, combined))

            ranked.sort(key=lambda x: x[1], reverse=True)
            return [r[0] for r in ranked[:count]]

        except Exception as e:
            logger.debug("Complementary selection failed: %s", e)
            return random.sample(candidates, min(count, len(candidates)))

    def compute_clustering(
        self,
        graph: Dict[str, Set[str]],
    ) -> float:
        """计算网络聚类系数.

        聚类系数 = 三角形的数量 / 可能的三角形数量

        Args:
            graph: {agent_id: {friend_ids}}

        Returns:
            聚类系数 (0-1)
        """
        if not graph:
            return 0.0

        total_coeff = 0.0
        node_count = 0

        for node, neighbors in graph.items():
            n = len(neighbors)
            if n < 2:
                continue

            # Count actual edges between neighbors
            actual = 0
            neighbors_list = list(neighbors)
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = neighbors_list[i], neighbors_list[j]
                    if b in graph.get(a, set()) or a in graph.get(b, set()):
                        actual += 1

            # Possible = n*(n-1)/2
            possible = n * (n - 1) / 2
            if possible > 0:
                total_coeff += actual / possible
                node_count += 1

        return total_coeff / max(node_count, 1)
