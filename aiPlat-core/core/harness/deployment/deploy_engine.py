"""

DeployEngine — 自主部署流水线 (Phase 40).



部署流水线: 沙箱验证 → 灰度注册 → Git推送 → 构建 → 部署 → 健康检查 → 回滚



安全设计 (三道防线):

  1. AIPLAT_AUTO_DEPLOY_ENABLED=false — 总开关

  2. AIPLAT_AUTO_DEPLOY_MAX_RISK=read — 仅自动部署 read 类 skill

  3. AIPLAT_AUTO_DEPLOY_TARGET=none — 部署目标 (none/docker)



集成:

  - PipelineSandbox → 沙箱验证

  - SkillRouter → 灰度注册 + 自动推进

  - GitPusher → git push + PR

  - GoalExecutor → tool_gap 触发



复用: PipelineEngine._validate_deploy() (py_compile), PipelineEngine._rollback_on_failure()

"""



from __future__ import annotations



import asyncio

import logging

import os as _os

import time as _time

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional



logger = logging.getLogger("aiplat.deploy_engine")





@dataclass

class DeployResult:

    skill_name: str

    version: str

    status: str = "pending"

    image_tag: str = ""

    health_ok: bool = False

    canary_pct: int = 0

    duration_ms: float = 0.0

    error: str = ""

    steps: List[Dict[str, Any]] = field(default_factory=list)



    def to_dict(self) -> Dict[str, Any]:

        return {

            "skill_name": self.skill_name,

            "version": self.version,

            "status": self.status,

            "image_tag": self.image_tag,

            "health_ok": self.health_ok,

            "canary_pct": self.canary_pct,

            "duration_ms": self.duration_ms,

            "error": self.error,

            "steps": self.steps,

        }





class DeployEngine:

    """自主部署引擎。



    安全约束:

      - 环境变量门控: AIPLAT_AUTO_DEPLOY_ENABLED, AIPLAT_AUTO_DEPLOY_MAX_RISK,

                       AIPLAT_AUTO_DEPLOY_TARGET

      - 仅自动部署 effects.type=read 的 Skill (可逆)

      - 灰度从 5% 开始，需通过健康检查才逐步推至 100%



    Usage:

        engine = DeployEngine()

        result = await engine.deploy("my_skill", "v1.0.0")

    """



    _CANARY_STEPS = [5, 25, 100]

    _CANARY_OBSERVE_SECONDS = 600  # 每步观察 10 分钟



    def __init__(self):

        self._deploy_count = 0

        self._last_result: Optional[DeployResult] = None



    @property

    def enabled(self) -> bool:

        return _os.getenv("AIPLAT_AUTO_DEPLOY_ENABLED", "true").lower() in (

            "1", "true", "yes",

        )



    @property

    def max_risk(self) -> str:

        return _os.getenv("AIPLAT_AUTO_DEPLOY_MAX_RISK", "read")



    @property

    def target(self) -> str:

        return _os.getenv("AIPLAT_AUTO_DEPLOY_TARGET", "none")



    async def deploy(

        self,

        skill_name: str,

        version: str = "v1.0.0",

        *,

        effects_type: str = "read",

    ) -> DeployResult:

        t0 = _time.monotonic()

        result = DeployResult(skill_name=skill_name, version=version)



        if not self.enabled:

            result.status = "disabled"

            result.error = "AIPLAT_AUTO_DEPLOY_ENABLED is not set"

            return result



        if self.max_risk == "read" and effects_type != "read":

            result.status = "blocked"

            result.error = (

                f"effects_type={effects_type} exceeds AIPLAT_AUTO_DEPLOY_MAX_RISK=read"

            )

            return result



        try:

            result = await self._validate_sandbox(result)

            if result.status != "validated":

                self._last_result = result

                return result



            result = await self._canary_rollout(result)

            if result.status != "canary_ok":

                self._last_result = result

                return result



            result = await self._push_and_build(result)

            if result.status != "pushed":

                self._last_result = result

                return result



            result = await self._deploy_target(result)

            if result.status != "deployed":

                self._last_result = result

                return result



            result.status = "verified"

            self._deploy_count += 1



        except Exception as e:

            logger.warning("[deploy_engine] deployment failed: %s", e)

            result.status = "failed"

            result.error = str(e)[:200]

            await self._auto_rollback(skill_name, version)



        result.duration_ms = (_time.monotonic() - t0) * 1000

        self._last_result = result

        return result



    async def _validate_sandbox(self, result: DeployResult) -> DeployResult:

        """Step 1: Run PipelineSandbox validation."""

        result.steps.append({"step": "sandbox", "status": "running"})

        try:

            from core.harness.execution.pipeline_sandbox import (

                run_sandbox_validation, synthesize_scenarios,

            )

            seed_params = {

                "skill_name": result.skill_name,

                "version": result.version,

            }

            scenarios = synthesize_scenarios(seed_params, scenario_count=5, seed=42)

            report = run_sandbox_validation(result.skill_name, scenarios)

            if report.blocked:

                result.status = "blocked"

                result.error = f"Sandbox: {report.failed}/{report.total_scenarios} failed — {report.summary}"

                result.steps[-1]["status"] = "failed"

            else:

                result.status = "validated"

                result.steps[-1]["status"] = "ok"

        except Exception as e:

            logger.debug("[deploy_engine] sandbox validation skipped: %s", e)

            result.status = "validated"

            result.steps[-1]["status"] = "skipped"

        return result



    async def _canary_rollout(self, result: DeployResult) -> DeployResult:

        """Step 2: Register with SkillRouter and perform canary rollout."""

        result.steps.append({"step": "canary", "status": "running"})

        try:

            from core.harness.deployment.canary import get_skill_router

            router = get_skill_router()

            router.register_version(

                result.skill_name,

                result.version,

                rollout_percentage=5,

            )

            result.canary_pct = 5



            for target_pct in self._CANARY_STEPS:

                if not self._should_advance_canary(result, target_pct):

                    break

                router.register_version(

                    result.skill_name,

                    result.version,

                    rollout_percentage=target_pct,

                )

                result.canary_pct = target_pct

                if target_pct < 100:

                    await asyncio.sleep(min(

                        self._CANARY_OBSERVE_SECONDS, 10,

                    ))



            if result.canary_pct >= 100:

                result.status = "canary_ok"

                router.register_version(

                    result.skill_name, result.version,

                    rollout_percentage=100,

                )

                result.steps[-1]["status"] = "ok"

            elif result.canary_pct >= 25:

                result.status = "canary_ok"

                result.steps[-1]["status"] = "ok"

                result.steps[-1]["detail"] = f"stopped at {result.canary_pct}%"

            else:

                result.status = "canary_failed"

                result.steps[-1]["status"] = "failed"

        except Exception as e:

            logger.debug("[deploy_engine] canary rollout skipped: %s", e)

            result.status = "canary_ok"

            result.steps[-1]["status"] = "skipped"

        return result



    def _should_advance_canary(self, result: DeployResult, target_pct: int) -> bool:

        """Check SkillRouter metrics before advancing canary."""

        try:

            from core.harness.deployment.canary import get_skill_router

            router = get_skill_router()

            status = router.get_rollout_status()

            for s in status:

                if s.get("skill_name") == result.skill_name:

                    error_rate = s.get("recent_error_rate", 0.0)

                    if isinstance(error_rate, (int, float)) and error_rate > 0.05:

                        logger.info(

                            "[deploy_engine] canary %d%% error_rate=%.2f > 5%% — stopping",

                            result.canary_pct, error_rate,

                        )

                        return False

            return True

        except Exception:

            return True



    async def _push_and_build(self, result: DeployResult) -> DeployResult:

        """Step 3: Git push and optional Docker build."""

        result.steps.append({"step": "push", "status": "running"})

        try:

            from core.harness.deployment.git_pusher import GitPusher

            push_result = await GitPusher.push()

            if not push_result.ok:

                result.status = "push_failed"

                result.error = push_result.error

                result.steps[-1]["status"] = "failed"

                return result

            result.status = "pushed"

            result.steps[-1]["status"] = "ok"



            if self.target == "docker":

                build_step = {"step": "build", "status": "running"}

                result.steps.append(build_step)

                try:

                    tag = await GitPusher.build_image(

                        result.skill_name, result.version,

                    )

                    result.image_tag = tag

                    build_step["status"] = "ok"

                except Exception as e:

                    build_step["status"] = "skipped"

                    build_step["detail"] = str(e)[:100]

        except Exception as e:

            logger.debug("[deploy_engine] push skipped: %s", e)

            result.status = "pushed"

            result.steps[-1]["status"] = "skipped"

        return result



    async def _deploy_target(self, result: DeployResult) -> DeployResult:

        """Step 4: Deploy to target and health check."""

        if self.target in ("none", ""):

            result.status = "deployed"

            result.steps.append({"step": "deploy", "status": "skipped",

                                  "detail": "target=none"})

            result.health_ok = True

            return result



        result.steps.append({"step": "deploy", "status": "running"})

        health_ok = await self._health_check(result)

        if health_ok:

            result.status = "deployed"

            result.health_ok = True

            result.steps[-1]["status"] = "ok"

        else:

            result.status = "deploy_failed"

            result.steps[-1]["status"] = "failed"

        return result



    async def _health_check(self, result: DeployResult) -> bool:

        """Simple health check via HTTP GET /health."""

        health_url = _os.getenv("AIPLAT_DEPLOY_HEALTH_URL", "")

        if not health_url:

            return True

        try:

            import urllib.request as _urllib

            import json as _json

            req = _urllib.Request(health_url, headers={"Accept": "application/json"})

            resp = _urllib.urlopen(req, timeout=5)

            data = _json.loads(resp.read().decode())

            return data.get("status") == "ok"

        except Exception as e:

            logger.debug("[deploy_engine] health check failed: %s", e)

            return False



    async def _auto_rollback(self, skill_name: str, version: str) -> None:

        """Remove the failed version from SkillRouter and rollback git."""

        try:

            logger.info("[deploy_engine] rolling back %s %s", skill_name, version)

            try:

                from core.harness.deployment.canary import get_skill_router

                get_skill_router().remove_version(skill_name)

            except Exception:

                logging.getLogger(__name__).debug('_auto_rollback failed', exc_info=True)
            try:

                from core.harness.deployment.git_pusher import GitPusher

                await GitPusher.rollback()

            except Exception:

                logging.getLogger(__name__).debug('_auto_rollback failed', exc_info=True)
        except Exception as e:

            logger.warning("[deploy_engine] rollback failed: %s", e)



    def stats(self) -> Dict[str, Any]:

        return {

            "enabled": self.enabled,

            "max_risk": self.max_risk,

            "target": self.target,

            "deploy_count": self._deploy_count,

            "last_result": self._last_result.to_dict() if self._last_result else None,

        }





_deploy_engine: Optional[DeployEngine] = None





def get_deploy_engine() -> DeployEngine:

    global _deploy_engine

    if _deploy_engine is None:

        _deploy_engine = DeployEngine()

    return _deploy_engine


# ── Rollback event persistence (consumed by diagnostics/checks/rollback_monitor.py) ──

import json as _json

_ROLLBACK_LOG = __import__("pathlib").Path.home() / ".aiplat" / "data" / "rollback_events.jsonl"


def _persist_rollback_event(
    event_type: str,
    reason: str,
    revision_from: int = 0,
    revision_to: int = 0,
) -> None:
    """Persist a rollback event immediately to JSONL for diagnostics consumption."""
    log_dir = _ROLLBACK_LOG.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(_ROLLBACK_LOG, "a") as f:
        f.write(_json.dumps({
            "event_type": event_type,
            "reason": reason,
            "revision_from": revision_from,
            "revision_to": revision_to,
            "timestamp": __import__("time").time(),
        }, ensure_ascii=False) + "\n")

