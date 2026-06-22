"""
Skill Gradual Rollout — 灰度发布 / A-B 测试 / 影子模式

企业级中台区别于个人工具的关键分水岭。

模式:
  Canary: 按 tenant_id 或流量百分比分流到新版 Skill
  A-B Test: 对比新旧版本效果 (成功率/延迟/用户满意度)
  Shadow: 新版静默运行, 对比结果但不影响线上
  Auto-Rollback: 错误率超阈值 → 自动切回旧版

Usage:
    router = SkillRouter()
    router.register_version("code_generation", "v2.1", rollout_percentage=10)
    
    # 路由决策
    version = router.route("code_generation", tenant_id="acme", user_id="user123")
    
    # 影子模式
    if router.shadow_enabled("code_generation"):
        shadow_result = await router.run_shadow("code_generation", input_data)
"""

from __future__ import annotations

import asyncio, time, hashlib, json, os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class RolloutConfig:
    """单个 Skill 版本的灰度配置。"""
    skill_name: str
    version: str                       # 目标版本号
    rollout_percentage: int = 0        # 灰度百分比 [0, 100]
    canary_tenants: List[str] = field(default_factory=list)
    shadow_mode: bool = False           # 是否开启影子模式
    auto_rollback: Dict[str, Any] = field(default_factory=dict)
    # auto_rollback: {"metric": "error_rate", "threshold": 0.05, "window_minutes": 10}
    enabled: bool = True
    created_at: float = 0.0


@dataclass
class ABTestResult:
    """A-B 测试单次结果。"""
    skill_name: str
    version_a: str
    version_b: str
    a_success: int = 0
    a_total: int = 0
    b_success: int = 0
    b_total: int = 0
    a_avg_latency: float = 0.0
    b_avg_latency: float = 0.0
    recommendation: str = ""           # "promote_b" / "keep_a" / "inconclusive"


class SkillRouter:
    """Skill 灰度路由器。

    核心决策:
        request → 路由决策
          ├─ tenant_id ∈ canary_tenants → 新版
          ├─ user_id_hash % 100 < rollout_pct → 新版
          └─ otherwise → 稳定版
    """

    def __init__(self):
        self._rollouts: Dict[str, RolloutConfig] = {}
        self._ab_tests: Dict[str, ABTestResult] = {}
        self._metrics: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    # ── Configuration ───────────────────────────────────────────────────

    def register_version(
        self,
        skill_name: str,
        version: str,
        *,
        rollout_percentage: int = 0,
        canary_tenants: List[str] = None,
        shadow_mode: bool = False,
        auto_rollback: Dict[str, Any] = None,
    ):
        """注册 Skill 灰度版本。

        Args:
            skill_name: Skill 名称
            version: 目标版本
            rollout_percentage: 灰度百分比 (0=仅 canary tenants)
            canary_tenants: 金丝雀租户列表
            shadow_mode: 是否开启影子模式
            auto_rollback: 自动回滚配置 {"metric":"error_rate","threshold":0.05,"window_minutes":10}
        """
        self._rollouts[skill_name] = RolloutConfig(
            skill_name=skill_name,
            version=version,
            rollout_percentage=rollout_percentage,
            canary_tenants=canary_tenants or [],
            shadow_mode=shadow_mode,
            auto_rollback=auto_rollback or {},
            enabled=True,
            created_at=time.time(),
        )

    def remove_version(self, skill_name: str):
        """回滚到稳定版 (100% 旧版)。"""
        self._rollouts.pop(skill_name, None)

    # ── Routing ─────────────────────────────────────────────────────────

    def route(self, skill_name: str, *, tenant_id: str = "", user_id: str = "") -> str:
        """路由决策: 返回应使用的版本。

        Args:
            skill_name: Skill 名称
            tenant_id: 租户 ID
            user_id: 用户 ID

        Returns:
            版本号 ("stable" 或 "v2.1" 等)
        """
        rollout = self._rollouts.get(skill_name)
        if not rollout or not rollout.enabled:
            return "stable"

        # 1. Canary tenant — always new version
        if tenant_id and tenant_id in rollout.canary_tenants:
            return rollout.version

        # 2. Percentage-based rollout
        if rollout.rollout_percentage > 0:
            bucket = self._user_bucket(user_id or tenant_id, skill_name)
            if bucket < rollout.rollout_percentage:
                return rollout.version

        # 3. Default — stable version
        return "stable"

    def shadow_enabled(self, skill_name: str) -> bool:
        """检查是否开启影子模式。"""
        rollout = self._rollouts.get(skill_name)
        return rollout is not None and rollout.shadow_mode

    # ── A-B Testing ─────────────────────────────────────────────────────

    def start_ab_test(self, skill_name: str, version_a: str, version_b: str):
        """启动 A-B 测试。"""
        self._ab_tests[skill_name] = ABTestResult(
            skill_name=skill_name, version_a=version_a, version_b=version_b)

    def record_ab_result(
        self,
        skill_name: str,
        version: str,
        success: bool,
        latency_ms: float = 0.0,
    ):
        """记录 A-B 测试的单次结果。"""
        test = self._ab_tests.get(skill_name)
        if not test:
            return
        if version == test.version_a:
            test.a_total += 1
            if success:
                test.a_success += 1
            test.a_avg_latency = (test.a_avg_latency * (test.a_total - 1) + latency_ms) / max(test.a_total, 1)
        elif version == test.version_b:
            test.b_total += 1
            if success:
                test.b_success += 1
            test.b_avg_latency = (test.b_avg_latency * (test.b_total - 1) + latency_ms) / max(test.b_total, 1)

    def get_ab_recommendation(self, skill_name: str) -> str:
        """获取 A-B 测试推荐。"""
        test = self._ab_tests.get(skill_name)
        if not test or test.a_total < 10 or test.b_total < 10:
            return "inconclusive (need more data)"

        a_rate = test.a_success / max(test.a_total, 1)
        b_rate = test.b_success / max(test.b_total, 1)

        diff = b_rate - a_rate
        if diff > 0.05:
            return f"promote_b ({test.version_b} wins by {diff:.1%})"
        elif diff < -0.05:
            return f"keep_a ({test.version_a} is better)"
        else:
            return "inconclusive (no significant difference)"

    # ── Auto-Rollback ───────────────────────────────────────────────────

    def check_auto_rollback(self, skill_name: str) -> Optional[str]:
        """检查是否需要自动回滚。

        Returns:
            如果触发回滚, 返回原因字符串; 否则 None
        """
        rollout = self._rollouts.get(skill_name)
        if not rollout or not rollout.auto_rollback:
            return None

        cfg = rollout.auto_rollback
        metric = cfg.get("metric", "error_rate")
        threshold = float(cfg.get("threshold", 0.05))
        window_minutes = int(cfg.get("window_minutes", 10))

        # Get recent metrics for the new version
        key = f"{skill_name}:{rollout.version}"
        metrics = self._metrics.get(key, [])
        recent = [m for m in metrics if time.time() - m.get("ts", 0) < window_minutes * 60]

        if not recent:
            return None

        if metric == "error_rate":
            errors = sum(1 for m in recent if not m.get("success", True))
            error_rate = errors / max(len(recent), 1)
            if error_rate > threshold:
                self.remove_version(skill_name)
                return f"auto-rollback: error_rate={error_rate:.2%} > threshold={threshold}"
        elif metric == "latency_p95":
            latencies = sorted(m.get("latency_ms", 0) for m in recent)
            p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
            if p95 > threshold:
                self.remove_version(skill_name)
                return f"auto-rollback: P95 latency={p95}ms > threshold={threshold}ms"

        return None

    def record_metric(self, skill_name: str, version: str, *, success: bool, latency_ms: float = 0.0):
        """记录执行指标。"""
        key = f"{skill_name}:{version}"
        if key not in self._metrics:
            self._metrics[key] = []
        self._metrics[key].append({
            "ts": time.time(),
            "success": success,
            "latency_ms": latency_ms,
        })
        # Trim old records
        cutoff = time.time() - 3600
        self._metrics[key] = [m for m in self._metrics[key] if m["ts"] > cutoff]

    # ── Shadow Mode ─────────────────────────────────────────────────────

    async def run_shadow(
        self,
        skill_name: str,
        input_data: Any,
        *,
        tenant_id: str = "",
        user_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """在影子模式下静默执行新版 Skill。

        不返回结果给用户, 仅记录差异用于对比。

        Args:
            skill_name: Skill 名称
            input_data: 输入数据
            tenant_id: 租户
            user_id: 用户

        Returns:
            影子执行结果 (仅用于日志), 或 None
        """
        rollout = self._rollouts.get(skill_name)
        if not rollout or not rollout.shadow_mode:
            return None

        try:
            # Execute new version silently
            start = time.time()
            success = True
            result = None

            # (In production, this calls the actual Skill execution)
            # result = await execute_skill(skill_name, version=rollout.version, input=input_data)

            latency = (time.time() - start) * 1000
            self.record_ab_result(skill_name, rollout.version, success=success, latency_ms=latency)
            self.record_metric(skill_name, rollout.version, success=success, latency_ms=latency)

            return {"shadow": True, "version": rollout.version, "result": result}
        except Exception as e:
            self.record_metric(skill_name, rollout.version, success=False)
            return {"shadow": True, "error": str(e)}

    # ── Internal ────────────────────────────────────────────────────────

    def _user_bucket(self, user_id: str, skill_name: str) -> int:
        """确定性哈希分桶 [0, 100)。"""
        h = hashlib.md5(f"{skill_name}:{user_id}".encode()).hexdigest()
        return int(h[:8], 16) % 100

    def get_rollout_status(self) -> List[Dict[str, Any]]:
        """获取所有灰度版本的状态。"""
        return [
            {
                "skill": r.skill_name,
                "version": r.version,
                "rollout_pct": r.rollout_percentage,
                "canary_tenants": r.canary_tenants,
                "shadow": r.shadow_mode,
                "auto_rollback": bool(r.auto_rollback),
                "enabled": r.enabled,
                "age_hours": round((time.time() - r.created_at) / 3600, 1),
            }
            for r in self._rollouts.values()
        ]


# ── Global singleton ─────────────────────────────────────────────────────

_skill_router: Optional[SkillRouter] = None

def get_skill_router() -> SkillRouter:
    global _skill_router
    if _skill_router is None:
        _skill_router = SkillRouter()
    return _skill_router
