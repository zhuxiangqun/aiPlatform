"""ControlProfile — 六维联合控制画像。

Harness 运行时所有模块（ModelTierRouter、ReActLoop、Compression、
ContextBus、GateSystem）通过 get_active_profile() 读取当前画像，
统一 D1-D6 维度的行为参数。

Design:
  - 数据类，可序列化/反序列化（JSON/YAML）
  - 类方法 interpolate() 支持多画像加权混合（解决硬切换震荡）
  - to_cache_key() 提供离散化稳定键（解决浮点哈希漂移）
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import List, Optional, Tuple
import hashlib

import numpy as np

# ── 字段分类常量（供 Interpolator 融合策略使用）──

FLOAT_FIELDS = frozenset({
    "temperature",
    "compression_strictness",
    "gate_strictness",
})
INT_FIELDS = frozenset({
    "context_layers",
    "context_max_sources",
    "max_parallel_agents",
})
ENUM_FIELDS = frozenset({
    "model_tier",
    "temperature_profile",
    "orchestration_mode",
    "tool_rank_by",
})
BOOL_FIELDS = frozenset({
    "episodic_injection",
    "semantic_injection",
    "require_schema_validation",
})
LIST_FIELDS = frozenset({
    "tool_whitelist",
})


@dataclass
class ControlProfile:
    """六维联合控制画像 — Harness 运行时的行为契约。

    Attributes by dimension:
      D1 Context:
        context_layers: ContextBus 层数 [1-10]
        context_max_sources: AdaptiveContextRouter 源数上限
      D2 Tools:
        tool_whitelist: 工具白名单 (None=全部开放)
        tool_rank_by: 工具排序策略 (static|success_rate|relevance)
      D3 Generation:
        model_tier: 模型层级 (T1-T5|auto|by_complexity)
        temperature_profile: 温度策略 (flat|anneal|explore_first)
        temperature: 基础温度值 [0.0-1.0]
      D4 Orchestration:
        orchestration_mode: 编排模式 (single|chain|tree|reflexion|auto)
        max_parallel_agents: 最大并行 Agent 数
      D5 Memory:
        compression_strictness: 压缩激进系数 (<1激进, =1默认, >1保守)
        episodic_injection: 是否注入过往会话摘要
        semantic_injection: 是否注入长期知识
      D6 Output:
        gate_strictness: 门控严格系数 (<1宽松, =1默认, >1严格)
        require_schema_validation: 是否强制输出 Schema 校验
    """

    # D1: Context
    context_layers: int = 3
    context_max_sources: int = 5

    # D2: Tools
    tool_whitelist: Optional[List[str]] = None
    tool_rank_by: str = "static"

    # D3: Generation
    model_tier: str = "auto"
    temperature_profile: str = "flat"
    temperature: float = 0.3

    # D4: Orchestration
    orchestration_mode: str = "auto"
    max_parallel_agents: int = 3

    # D5: Memory
    compression_strictness: float = 1.0
    episodic_injection: bool = True
    semantic_injection: bool = True

    # D6: Output
    gate_strictness: float = 1.0
    require_schema_validation: bool = True

    # D7: Knowledge scope
    collection_filter: Optional[str] = None  # restrict KB to specific collection

    # D8: Persona
    persona_file: Optional[str] = None  # SOUL.md path for role-specific personality

    # D9: Tool scope
    toolset: Optional[str] = None  # "full" | "readonly" | "voice_only"

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """导出为 JSON 兼容字典。"""
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ControlProfile":
        """从字典反序列化。丢弃未知字段，缺失字段使用默认值。"""
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    # ── 向量化（供 Interpolator 语义匹配）──

    def to_full_vector(self) -> np.ndarray:
        """六维数值向量 (9 维)，用于与预设画像的语义向量做余弦相似度匹配。"""
        vec = [
            float(self.context_layers) / 10.0,
            float(self.context_max_sources) / 10.0,
            self.temperature,
            float(self.max_parallel_agents) / 10.0,
            self.compression_strictness,
            self.gate_strictness,
            _encode_tier(self.model_tier),
            _encode_orchestration(self.orchestration_mode),
            _encode_temp_profile(self.temperature_profile),
        ]
        return np.array(vec, dtype=np.float32)

    # ── 缓存键（供 CacheAwareRouter）──

    def to_cache_key(self) -> str:
        """稳定缓存键（仅 D1+D2 维度，离散化防浮点哈希漂移）。

        CacheAwareRouter 通过 SHA256 比对此键判断 cache_control 前缀是否可复用。
        返回格式: "l{layers}|s{sources}|tr{tool_rank_idx}"
        """
        parts = [
            f"l{int(round(self.context_layers))}",
            f"s{int(round(self.context_max_sources))}",
            f"tr{['static', 'success_rate', 'relevance'].index(self.tool_rank_by)}",
        ]
        return "|".join(parts)

    def cache_key_hash(self) -> str:
        """to_cache_key() 的 SHA256 摘要（取前 16 位 hex）。"""
        return hashlib.sha256(self.to_cache_key().encode()).hexdigest()[:16]

    # ── 插值（类方法，纯函数，不依赖外部状态）──

    @classmethod
    def interpolate(
        cls,
        profiles: List["ControlProfile"],
        weights: List[float],
    ) -> "ControlProfile":
        """从多个画像按权重加权混合，生成新画像。

        Args:
            profiles: 参与混合的画像列表（至少 1 个）。
            weights:  对应权重列表（与 profiles 等长），内部自动归一化。

        Returns:
            新 ControlProfile 实例。每个字段按类型采用不同融合策略：
              - float:  加权平均
              - int:    加权平均后四舍五入
              - enum:   排除 'auto' 后 argmax
              - bool:   加权平均 >= 0.5 → True
              - list:   并集 + 累计权重降序截断至 top-10
        """
        w = np.array(weights, dtype=np.float64)
        w = w / w.sum()

        kwargs = {}
        for f in fields(cls):
            name = f.name
            raw = [getattr(p, name) for p in profiles]

            if name in FLOAT_FIELDS:
                kwargs[name] = float(np.average(raw, weights=w))
            elif name in INT_FIELDS:
                kwargs[name] = int(round(float(np.average(raw, weights=w))))
            elif name in ENUM_FIELDS:
                kwargs[name] = _fuse_enum(raw, w)
            elif name in BOOL_FIELDS:
                score = float(np.average([1.0 if v else 0.0 for v in raw], weights=w))
                kwargs[name] = score >= 0.5
            elif name in LIST_FIELDS:
                kwargs[name] = _fuse_list(raw, w)

        return cls(**kwargs)


# ── 融合辅助函数 ──

def _fuse_enum(values: list, weights: np.ndarray) -> str:
    """枚举融合：排除 'auto'（不表态）后在剩余值中 argmax 权重。"""
    non_auto = [(v, wt) for v, wt in zip(values, weights) if v != "auto"]
    if not non_auto:
        return "auto"
    vals, wts = zip(*non_auto)
    return vals[int(np.argmax(wts))]


def _fuse_list(values: list, weights: np.ndarray) -> Optional[List[str]]:
    """列表融合：并集 + 累计权重降序 + 截断 top-10。

    None 表示"全部开放"，不参与合并。全部 None → 返回 None。
    """
    concrete = [(v, wt) for v, wt in zip(values, weights) if v is not None]
    if not concrete:
        return None
    merged: dict = {}
    for items, wt in concrete:
        for item in items:
            merged[item] = merged.get(item, 0.0) + float(wt)
    return sorted(merged.keys(), key=lambda x: merged[x], reverse=True)[:10]


def _encode_tier(tier: str) -> float:
    return {"T1": 0.1, "T2": 0.3, "T3": 0.5, "T4": 0.7, "T5": 0.9}.get(tier, 0.5)


def _encode_orchestration(mode: str) -> float:
    return {"single": 0.1, "chain": 0.3, "tree": 0.5, "reflexion": 0.7, "auto": 0.5}.get(mode, 0.5)


def _encode_temp_profile(profile: str) -> float:
    return {"flat": 0.3, "anneal": 0.5, "explore_first": 0.7}.get(profile, 0.5)


# ── Interpolator ────────────────────────────────────────────


class ControlProfileInterpolator:
    """画像插值器 — 在预设画像之间做连续加权混合。

    核心职责: 给定 task_embedding + task_type + priority，返回最优插值画像。

    Design:
      - 内部缓存 sha256(task_vec) → profile（LRU, 128 entries）
      - softmax 温度 2.0 放大差异，防止所有画像权重趋同
    """

    def __init__(self, registry: Optional["ProfileRegistry"] = None):
        from .profile_registry import ProfileRegistry
        self._registry = registry or ProfileRegistry.instance()

    def resolve(
        self,
        task_embedding: np.ndarray,
        task_type: Optional[str] = None,
        priority: Optional[str] = None,
        k: int = 3,
    ) -> "ControlProfile":
        """一次调用完成: 相似度匹配 → 插值 → priority 调权。"""
        return self._registry.resolve_with_embedding(
            task_embedding=task_embedding,
            task_type=task_type,
            priority=priority,
            k=k,
        )
