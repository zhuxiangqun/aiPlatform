"""ProfileRegistry — 全局画像注册表（单例）。



职责:

  1. 从 control_presets.yaml 加载预设画像

  2. 根据 task_type + priority 解析活跃画像

  3. 为 Interpolator 提供预设语义向量和 task → profile 映射

  4. get_active_profile() 是消费者的统一入口



Design:

  - 所有 kernel/runtime 导入均为惰性（函数体内），避免循环依赖

  - RunContext 是 dataclass，使用属性访问而非 dict 方式

  - 目录不存在时自动 mkdir -p

"""



from __future__ import annotations



import logging

import os

import dataclasses

from pathlib import Path

from typing import Any, Dict, List, Optional



import numpy as np



from .control_profile import ControlProfile



logger = logging.getLogger("aiplat.profile_registry")





def _ensure_profile_dir() -> Path:

    """确保画像目录存在。"""

    p = Path(os.getenv(

        "AIPLAT_PROFILE_DIR",

        str(Path.home() / ".aiplat" / "profiles"),

    ))

    p.mkdir(parents=True, exist_ok=True)

    return p





_DEFAULT_PROFILE = ControlProfile()





class ProfileRegistry:

    """全局画像注册表 — 惰性加载预设，运行时动态解析。



    Usage:

        registry = ProfileRegistry.instance()

        profile = registry.resolve(task_type="code_generation", priority="normal")

    """



    _instance: Optional["ProfileRegistry"] = None



    def __init__(self, config_path: Optional[str] = None):

        self._presets: Dict[str, ControlProfile] = {}

        self._task_hints: Dict[str, str] = {}

        self._embeddings: Dict[str, np.ndarray] = {}  # preset_name → semantic embedding

        self._loaded = False

        self._load_presets(config_path)



    # ── 单例 ──



    @classmethod

    def instance(cls) -> "ProfileRegistry":

        if cls._instance is None:

            cls._instance = cls()

        return cls._instance



    @classmethod

    def reset(cls) -> None:

        """仅用于测试 — 重置单例。"""

        cls._instance = None



    # ── 加载 ──



    def _load_presets(self, config_path: Optional[str] = None) -> None:

        """从 control_presets.yaml 加载预设画像和 task_hints 映射。"""

        if self._loaded:

            return

        self._loaded = True



        if not config_path:

            config_path = str(_ensure_profile_dir() / "control_presets.yaml")



        try:

            import yaml

            path = Path(config_path)

            if not path.is_file():

                logger.info("No preset profiles at %s — using defaults", config_path)

                return



            with open(path) as f:

                data = yaml.safe_load(f) or {}



            presets_raw = data.get("presets", {})

            for name, cfg in presets_raw.items():

                if not isinstance(cfg, dict):

                    continue

                try:

                    self._presets[name] = ControlProfile.from_dict(cfg)

                    # 预计算语义向量（从名称+描述文本）

                    desc = cfg.get("description", name) if isinstance(cfg, dict) else name

                    self._embeddings[name] = self._compute_embedding(f"{name}: {desc}")

                except Exception as e:

                    logger.warning("Failed to load preset '%s': %s", name, e)



            hints_raw = data.get("task_hints", {})

            for task_type, preset_name in hints_raw.items():

                if preset_name and isinstance(preset_name, str):

                    self._task_hints[task_type] = preset_name



            logger.info("Loaded %d presets + %d task_hints from %s",

                        len(self._presets), len(self._task_hints), config_path)



        except Exception as e:

            logger.warning("Failed to load profile presets: %s", e)



    def reload(self) -> None:

        """强制重新加载（热加载支持）。"""

        self._loaded = False

        self._presets.clear()

        self._task_hints.clear()

        self._load_presets()



    # ── 查询 ──



    def get_preset(self, name: str) -> Optional[ControlProfile]:

        return self._presets.get(name)



    def list_presets(self) -> List[str]:

        return sorted(self._presets.keys())



    def get_default(self) -> ControlProfile:

        return self._presets.get("default", _DEFAULT_PROFILE)



    # ── 核心解析 ──



    def resolve(

        self,

        task_type: Optional[str] = None,

        priority: Optional[str] = None,

        profile_name: Optional[str] = None,

    ) -> ControlProfile:

        """解析当前任务的活跃画像。



        优先级链:

          1. profile_name 显式指定 → 返回对应预设

          2. task_type 命中 task_hints → 返回对应预设

          3. task_type 名直接匹配预设名 → 返回该预设

          4. priority 调权（elevated/critical → 混合 safety_critical）

          5. 兜底 → 返回 default

        """

        if profile_name:

            preset = self.get_preset(profile_name)

            if preset:

                return self._apply_priority(preset, priority)



        if task_type and task_type in self._task_hints:

            preset = self.get_preset(self._task_hints[task_type])

            if preset:

                return self._apply_priority(preset, priority)



        if task_type:

            preset = self.get_preset(task_type)

            if preset:

                return self._apply_priority(preset, priority)



        return self._apply_priority(self.get_default(), priority)



    def _apply_priority(self, base: ControlProfile,

                        priority: Optional[str]) -> ControlProfile:

        """按 priority 混合 safety_critical 画像。



        critical → 混合 30% safety_critical

        elevated → 混合 10% safety_critical

        normal / None → 不做混合

        """

        if priority not in ("elevated", "critical"):

            return base



        safety = self.get_preset("safety_critical")

        if not safety:

            return base



        blend = 0.3 if priority == "critical" else 0.1

        return ControlProfile.interpolate(

            [base, safety],

            [1.0 - blend, blend],

        )



    def resolve_with_embedding(

        self,

        task_embedding: np.ndarray,

        task_type: Optional[str] = None,

        priority: Optional[str] = None,

        k: int = 3,

    ) -> ControlProfile:

        """基于语义向量的画像解析（PR #2 中使用）。



        策略:

          1. 先用 task_type 做精确匹配（显式预设或 task_hints）

          2. 精确匹配命中（且不是 default）→ 直接返回

          3. 精确匹配未命中 → 降级到语义插值

        """

        # Step 1: 尝试精确匹配（不应用 priority，仅获取 base）

        base = self.resolve(task_type=task_type, priority=None, profile_name=None)



        # Step 2: 精确匹配命中非 default → 应用 priority 后返回

        if base != self.get_default():

            return self._apply_priority(base, priority)



        # Step 3: 未命中 → 降级到语义插值

        if task_embedding is not None and task_embedding.any():

            base = self._interpolate_by_similarity(task_embedding, k)

        else:

            base = self.get_default()



        return self._apply_priority(base, priority)



    def _interpolate_by_similarity(self,

                                   task_vec: np.ndarray,

                                   k: int = 3,

                                   ) -> ControlProfile:

        """语义相似度 top-k 插值。"""

        if len(self._presets) <= 1 or not self._embeddings:

            return self.get_default()



        similarities: List[tuple] = []

        task_norm = np.linalg.norm(task_vec)

        if task_norm == 0:

            return self.get_default()



        for name, preset_emb in self._embeddings.items():

            if name in ("default",):

                continue

            if not preset_emb.any() or np.linalg.norm(preset_emb) == 0:

                continue

            sim = float(np.dot(task_vec, preset_emb) / (

                task_norm * np.linalg.norm(preset_emb) + 1e-8))

            similarities.append((sim, name))



        if not similarities:

            return self.get_default()



        similarities.sort(reverse=True)

        top_k = similarities[:k]

        sims = np.array([s for s, _ in top_k], dtype=np.float64)



        # softmax 权重（温度 0.5 = 放大差异，防权重过于平均）

        sims_exp = np.exp(sims * 2.0)

        weights = sims_exp / sims_exp.sum()



        profiles = []

        valid_weights = []

        for (_, name), w in zip(top_k, weights):

            preset = self._presets.get(name)

            if preset:

                profiles.append(preset)

                valid_weights.append(w)



        if not profiles:

            return self.get_default()



        return ControlProfile.interpolate(profiles, valid_weights)



    def _compute_embedding(self, text: str) -> np.ndarray:

        """计算预设画像的语义向量（从描述文本，用于与 task_embedding 做余弦相似度匹配）。"""

        try:

            from core.harness.memory.compression import get_cached_embedding

            emb = get_cached_embedding(text[:500])

            if emb is not None:

                return np.array(emb, dtype=np.float32)

        except Exception:

            logging.getLogger(__name__).debug('_compute_embedding failed', exc_info=True)
        return np.zeros(0, dtype=np.float32)



    # ── 运行时注册（扩展点）──



    def register_preset(self, name: str, profile: ControlProfile) -> None:

        """运行时注册/覆盖自定义画像。"""

        self._presets[name] = profile





# ── 消费者统一入口 ──────────────────────────────────────────────





def get_active_profile() -> ControlProfile:

    """获取当前执行上下文中活跃的 ControlProfile。



    优先级:

      0. Session override (/profile 命令) → ProfileRegistry.get_preset(name)

      1. ReActLoop._config.control_profile（最强优先级）

      2. RunContext.metadata["control_profile"]（dataclass 属性访问）

      3. ProfileRegistry.get_default()（兜底）



    所有 Harness 模块通过此函数读取画像，不关心画像来源。

    所有 kernel/runtime 导入均为惰性（函数体内），避免循环依赖。

    使用 getattr 防 _config.control_profile 属性不存在。

    """



    # 0. Session profile override (/profile command)

    override_name = get_profile_override()

    if override_name:

        if override_name.startswith("_auto_bump_"):

            # Auto-bump: check _auto_bump_profiles dict first (most reliable)

            bumped = _auto_bump_profiles.get("_global")

            if bumped:

                return bumped

            # Fallback: try ReActLoop._config.control_profile

            try:

                from core.harness.kernel.runtime import get_kernel_runtime

                runtime = get_kernel_runtime()

                active_loop = getattr(runtime, "_active_loop", None)

                if active_loop is not None and hasattr(active_loop, "_config"):

                    profile = getattr(active_loop._config, "control_profile", None)

                    if isinstance(profile, ControlProfile):

                        return profile

            except (ImportError, AttributeError):

                pass  # noqa: optional-dependency

        else:

            preset = ProfileRegistry.instance().get_preset(override_name)

            if preset:

                return preset



    # 1. ReActLoop 活跃实例（getattr 防空指针）

    try:

        from core.harness.kernel.runtime import get_kernel_runtime

        runtime = get_kernel_runtime()

        active_loop = getattr(runtime, "_active_loop", None)

        if active_loop is not None and hasattr(active_loop, "_config"):

            profile = getattr(active_loop._config, "control_profile", None)

            if isinstance(profile, ControlProfile):

                return profile

    except (ImportError, AttributeError):

        pass  # noqa: optional-dependency



    # 2. RunContext.metadata（dataclass 属性访问）

    try:

        from core.harness.kernel.runtime import get_kernel_runtime

        runtime = get_kernel_runtime()

        run_ctx = getattr(runtime, "run_context", None)

        if run_ctx is not None and hasattr(run_ctx, "metadata"):

            profile_data = run_ctx.metadata.get("control_profile")

            if isinstance(profile_data, ControlProfile):

                return profile_data

            if isinstance(profile_data, dict):

                return ControlProfile.from_dict(profile_data)

    except (ImportError, AttributeError):

        pass  # noqa: optional-dependency



    # 3. 兜底

    return ProfileRegistry.instance().get_default()





# ── 故障归因 ──────────────────────────────────────────────────



# 每个请求的故障域（D1-D6），在 Gate/Hook 拦截时自动设置

# 值: "D1_context" | "D2_tools" | "D3_generation" |

#      "D4_orchestration" | "D5_memory" | "D6_output"

_last_failure_domain: Optional[str] = None





def set_failure_domain(domain: str) -> None:

    """设置当前请求的主要故障域。



    在 Gate 拦截、Hook 触发、Circuit Breaker 跳闸时调用。

    SECI Engine 在提取知识原子时读取此字段做聚合归因。

    """

    global _last_failure_domain

    _last_failure_domain = domain





def get_last_failure_domain() -> Optional[str]:

    """获取当前请求的主要故障域。读取后不清除。"""

    return _last_failure_domain





def clear_failure_domain() -> None:

    """清除故障域（新请求开始时调用）。"""

    global _last_failure_domain

    _last_failure_domain = None





# ── Session Profile Override (/profile command) ─────────────────



_profile_overrides: Dict[str, str] = {}

_auto_bump_profiles: Dict[str, ControlProfile] = {}  # session_id → bumped profile instance



def set_profile_override(name: str, session_id: str = "_global") -> None:

    """Set a session-level profile override. /profile code_generation"""

    _profile_overrides[session_id] = name



def get_profile_override(session_id: str = "_global") -> Optional[str]:

    """Get session-level profile override, or None."""

    return _profile_overrides.get(session_id)



def clear_profile_override(session_id: str = "_global") -> None:

    _profile_overrides.pop(session_id, None)



def list_profile_overrides() -> Dict[str, str]:

    return dict(_profile_overrides)





# ── D3 Auto-Bump (failure feedback loop) ───────────────────────



def auto_bump_model_tier() -> Optional[str]:

    """当 D3_generation 故障时, 自动升一级 model_tier.



    从 get_active_profile() 读取当前画像 → 升 tier → 写入 session override.

    返回新 tier 名称，或 None (已是 T5 或无画像)。

    """

    profile = get_active_profile()

    current = profile.model_tier

    if current in ("auto", "by_complexity", ""):

        return None



    tier_order = ["T1", "T2", "T3", "T4", "T5"]

    try:

        idx = tier_order.index(current)

    except ValueError:

        return None



    if idx >= len(tier_order) - 1:

        return None  # already T5



    new_tier = tier_order[idx + 1]

    new_profile = ControlProfile.from_dict(profile.to_dict())

    new_profile.model_tier = new_tier

    # 存入 session override + auto-bump profile dict

    set_profile_override("_auto_bump_" + new_tier)

    _auto_bump_profiles["_global"] = new_profile

    # 同时注入当前激活的 ReActLoop._config

    try:

        from core.harness.kernel.runtime import get_kernel_runtime

        runtime = get_kernel_runtime()

        active_loop = getattr(runtime, "_active_loop", None)

        if active_loop is not None and hasattr(active_loop, "_config"):

            active_loop._config.control_profile = new_profile

    except Exception:

        logging.getLogger(__name__).debug('auto_bump_model_tier failed', exc_info=True)


    return new_tier





# ── A/B Profile Comparison ─────────────────────────────────────



def compare_profiles(a: str, b: str) -> Dict[str, Any]:

    """Compare two profiles side-by-side for A/B testing.



    Args:

        a: 画像名 A (如 "code_generation")

        b: 画像名 B (如 "safety_critical")



    Returns:

        {

            "a": {"name": ..., "profile": {...}},

            "b": {"name": ..., "profile": {...}},

            "diff": {field: {"a": ..., "b": ..., "delta": ...}}

        }

    """

    reg = ProfileRegistry.instance()

    pa = reg.get_preset(a)

    pb = reg.get_preset(b)



    result = {

        "a": {"name": a, "profile": pa.to_dict() if pa else None},

        "b": {"name": b, "profile": pb.to_dict() if pb else None},

        "diff": {},

    }



    if not pa or not pb:

        return result



    for f in dataclasses.fields(ControlProfile):

        name = f.name

        va = getattr(pa, name)

        vb = getattr(pb, name)

        if va != vb:

            result["diff"][name] = {"a": va, "b": vb}



    return result


