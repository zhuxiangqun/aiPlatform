"""
AgentNetwork — Agent 关系网络分析与演化追踪 (EvoMap 自组织对齐)

基于 Agent 之间的协作关系构建网络图，分析:
  - 聚类系数: 小圈子 vs 开放网络
  - 枢纽节点: 识别影响力最大的 Agent
  - 演化追踪: 网络结构如何随时间变化

与 EvoMap 实验二对齐:
  只看到社交信息 → 聚类系数 ~0.53 (小圈子)
  加入任务信息 → 聚类系数 ~0.28 (开放网络，接近随机 0.27)

调用者: AgentNetworkPanel 前端 / REST API
"""

from __future__ import annotations

import json as _json
import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class NetworkNode:
    agent_id: str
    degree: int = 0                     # 连接数
    betweenness: float = 0.0            # 介数中心性
    hub_score: float = 0.0              # 枢纽度
    primary_domain: str = ""
    accuracy: float = 0.0
    actions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "degree": self.degree,
            "betweenness": round(self.betweenness, 4),
            "hub_score": round(self.hub_score, 4),
            "primary_domain": self.primary_domain,
            "accuracy": round(self.accuracy, 3),
            "actions": self.actions,
        }


@dataclass
class NetworkSnapshot:
    """网络快照 (用于演化追踪)."""
    timestamp: float
    node_count: int
    edge_count: int
    clustering_coefficient: float
    hub_nodes: List[NetworkNode] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "clustering_coefficient": round(self.clustering_coefficient, 4),
            "hub_nodes": [h.to_dict() for h in self.hub_nodes[:5]],
            "summary": self.summary,
        }


# ── AgentNetwork ────────────────────────────────────────────────────────────

class AgentNetwork:
    """Agent 关系网络分析.

    使用方式:
        net = AgentNetwork()
        nodes = await net.analyze(agent_ids=["a1","a2","a3"])
        snapshots = await net.evolution_tracking(agent_ids, interval_hours=24, count=10)
    """

    def __init__(self):
        self._snapshots: Dict[str, List[NetworkSnapshot]] = {}
        self._network_file = ""
        try:
            import os
            self._network_file = os.path.expanduser("~/.aiplat/agent_network.json")
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    async def analyze(
        self,
        agent_ids: List[str],
        *,
        lookback_hours: float = 168.0,
    ) -> List[NetworkNode]:
        """分析 Agent 关系网络.

        Args:
            agent_ids: 要分析的 Agent ID 列表
            lookback_hours: 回顾时间窗口

        Returns:
            网络节点列表 (含枢纽度排序)
        """
        try:
            from core.harness.learning.agent_specialization import AgentSpecialization
            from core.harness.learning.partner_selector import PartnerSelector

            spec = AgentSpecialization()
            selector = PartnerSelector()

            nodes: List[NetworkNode] = []
            degrees: Dict[str, int] = {}
            edges: Set[Tuple[str, str]] = set()

            for aid in agent_ids:
                vec = await spec.compute(aid, lookback_hours=lookback_hours)
                total_success = sum(s.success_count for s in vec.domains.values())
                accuracy = total_success / max(vec.total_actions, 1)

                # Find best partners
                partners = await selector.select(
                    aid,
                    [a for a in agent_ids if a != aid],
                    mode="capability",
                    count=5,
                )

                degrees[aid] = len(partners)
                for p in partners:
                    edges.add(tuple(sorted([aid, p])))

                nodes.append(NetworkNode(
                    agent_id=aid,
                    degree=len(partners),
                    primary_domain=vec.primary_domain,
                    accuracy=accuracy,
                    actions=vec.total_actions,
                ))

            # Compute hub scores (PageRank-like)
            total_edges = max(len(edges), 1)
            for node in nodes:
                node.hub_score = node.degree / total_edges

            # Sort by hub score
            nodes.sort(key=lambda n: n.hub_score, reverse=True)
            return nodes

        except Exception as e:
            logger.warning("Network analysis failed: %s", e)
            return []

    async def evolution_tracking(
        self,
        agent_ids: List[str],
        *,
        interval_hours: float = 24.0,
        count: int = 10,
    ) -> List[NetworkSnapshot]:
        """追踪网络演化.

        按时间间隔生成多张网络快照，观察网络结构的演化趋势。
        """
        snapshots: List[NetworkSnapshot] = []

        for i in range(count):
            lookback = (count - i) * interval_hours
            if lookback <= 0:
                continue

            nodes = await self.analyze(agent_ids, lookback_hours=lookback)
            if not nodes:
                continue

            # Compute clustering coefficient
            graph: Dict[str, Set[str]] = {}
            for node in nodes:
                graph[node.agent_id] = set()
            from core.harness.learning.partner_selector import PartnerSelector
            selector = PartnerSelector()
            clustering = selector.compute_clustering(graph)

            snapshot = NetworkSnapshot(
                timestamp=_time.time(),
                node_count=len(nodes),
                edge_count=sum(n.degree for n in nodes) // 2,
                clustering_coefficient=clustering,
                hub_nodes=nodes[:5],
                summary=(
                    f"节点={len(nodes)}, 边={sum(n.degree for n in nodes)//2}, "
                    f"聚类系数={clustering:.3f}"
                ),
            )
            snapshots.append(snapshot)

        # Persist
        self._save_snapshots(snapshots)
        return snapshots

    def _save_snapshots(self, snapshots: List[NetworkSnapshot]) -> None:
        """持久化网络快照."""
        try:
            if not self._network_file:
                return
            import os
            os.makedirs(os.path.dirname(self._network_file), exist_ok=True)
            with open(self._network_file, "w") as f:
                _json.dump([s.to_dict() for s in snapshots], f, ensure_ascii=False, indent=2)
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    def load_snapshots(self) -> List[Dict[str, Any]]:
        """加载历史网络快照."""
        try:
            if not self._network_file:
                return []
            import os
            if not os.path.exists(self._network_file):
                return []
            with open(self._network_file) as f:
                return _json.load(f)
        except Exception:
            return []
