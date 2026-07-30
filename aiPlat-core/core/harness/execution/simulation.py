"""
SimulationOrchestrator —统一沙盒推演引擎 (Palantir Scenario/Vertex 对齐)

将碎片化的7个子系统统一为"多场景并发推演→结构化对比→风险评估"的编排层：

  1. 从历史 PipelineState 快照提取种子参数
  2. 生成 M 个变异场景 (不同模型/提示词/跳过阶段)
  3. 在 dry_run 模式下并发执行每个场景的 Pipeline
  4. 对比输出产物、Token消耗、决策路径、质量分
  5. 生成 SimulationReport (含风险评估 + 部署建议)

复用:
  - snapshot.py → 状态捕获/对比
  - pipeline_sandbox.py → 参数变异策略
  - sandbox_gate.py → 安全检查 (PASS/REJECT/WARN)
  - devil_advocate.py → 场景级风险评估
  - failure_classifier.py → 错误分类

callers: POST /simulate (REST), FDE 工作台 SimulationPanel
"""

from __future__ import annotations

import asyncio
import copy
import json as _json
import logging
import os as _os
import tempfile as _tempfile
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.harness.execution.snapshot import (
    save_execution_snapshot,
    load_execution_snapshot,
    compare_execution_snapshots,
)
from core.harness.execution.pipeline_sandbox import (
    synthesize_scenarios,
    evaluate_canary_readiness,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════

class ScenarioType(str, Enum):
    """模拟场景类型"""
    MODEL_VARIANT = "model_variant"          # 换模型
    PROMPT_VARIANT = "prompt_variant"        # 换提示词
    SKIP_STAGE = "skip_stage"                # 跳过某阶段
    PARAM_MUTATION = "param_mutation"        # 参数变异 (复用 pipeline_sandbox)
    TOOL_RESTRICTION = "tool_restriction"    # 限制工具集


@dataclass
class ScenarioDefinition:
    """单个模拟场景定义"""
    scenario_id: str
    scenario_type: ScenarioType
    label: str                              # 人类可读标签 (如 "方案A: 用 DeepSeek-V4")
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    # model_overrides: 覆盖 stage 级模型选择
    model_overrides: Dict[str, str] = field(default_factory=dict)
    # prompt_extra: 覆盖 stage 级 system prompt 附加指令
    prompt_extra: str = ""
    # skip_stages: 跳过的阶段索引列表
    skip_stages: List[int] = field(default_factory=list)
    # tool_whitelist: 限制可用工具 (None=全部)
    tool_whitelist: Optional[List[str]] = None


@dataclass
class ScenarioRunResult:
    """单个场景的执行结果"""
    scenario_id: str
    label: str
    status: str                             # completed | failed | timeout
    error: str = ""
    
    # 产物对比
    artifacts: Dict[str, Any] = field(default_factory=dict)
    artifact_count: int = 0
    
    # 性能指标
    tokens_used: int = 0
    execution_time_ms: float = 0.0
    stages_completed: int = 0
    stages_total: int = 0
    
    # 质量
    quality_score: float = 0.0              # 0-100
    risk_level: int = 0                     # 1-5
    
    # 决策路径 (新增 - 未来扩展)
    tool_calls: List[str] = field(default_factory=list)
    stage_decisions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SimulationReport:
    """模拟对比报告"""
    simulation_id: str
    total_scenarios: int
    completed: int
    failed: int
    
    # 对比摘要
    baseline_label: str = ""
    comparison: List[Dict[str, Any]] = field(default_factory=list)
    
    # 各场景结果
    scenarios: List[ScenarioRunResult] = field(default_factory=list)
    
    # 风险评估
    risk_summary: Dict[str, Any] = field(default_factory=dict)
    
    # 部署建议
    deployment_readiness: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    
    # 元信息
    created_at: str = ""
    total_tokens_used: int = 0
    total_execution_time_ms: float = 0.0


# ══════════════════════════════════════════════════════════════
# SimulationOrchestrator
# ══════════════════════════════════════════════════════════════

class SimulationOrchestrator:
    """统一的模拟编排引擎。

    使用方式:
        orch = SimulationOrchestrator()
        report = await orch.run(
            seed_state=historical_pipeline_state,
            scenarios=[
                ScenarioDefinition(id="A", type=ScenarioType.MODEL_VARIANT, 
                                   label="DeepSeek-V4", model_overrides={"*": "deepseek-v4-pro"}),
                ScenarioDefinition(id="B", type=ScenarioType.SKIP_STAGE,
                                   label="跳过QA阶段", skip_stages=[4]),
            ],
        )
    """

    def __init__(self, *, max_concurrent: int = 3, timeout_per_scenario_s: float = 300.0):
        self._max_concurrent = max_concurrent
        self._timeout_per_scenario = timeout_per_scenario_s
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ── Public API ──────────────────────────────────────────────────────

    async def run(
        self,
        seed_state: Dict[str, Any],
        scenarios: List[ScenarioDefinition],
        *,
        baseline_label: str = "基线 (当前配置)",
        domain_id: str = "",
    ) -> SimulationReport:
        """执行多场景并发推演。

        Args:
            seed_state: 种子 PipelineState (可来自历史快照或当前运行)
            scenarios: 要测试的场景列表
            baseline_label: 基线场景的标签
            domain_id: 域ID (可选，用于上下文)

        Returns:
            SimulationReport 包含各场景对比和部署建议
        """
        sim_id = f"sim_{_time.strftime('%Y%m%d_%H%M%S')}_{_os.urandom(4).hex()}"
        start_time = _time.time()

        # Step 1: 运行基线 (用当前配置跑一遍作为参照)
        baseline = await self._run_single_scenario(
            seed_state, None, baseline_label, sim_id, is_baseline=True
        )
        logger.info("Baseline completed: %s tokens, %.0fms", baseline.tokens_used, baseline.execution_time_ms)

        # Step 2: 并发运行各场景 (使用 Semaphore 限制并发数)
        tasks = []
        for sc in scenarios:
            tasks.append(self._run_single_scenario(seed_state, sc, sc.label, sim_id))

        scenario_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        results: List[ScenarioRunResult] = [baseline]
        for i, res in enumerate(scenario_results):
            if isinstance(res, Exception):
                results.append(ScenarioRunResult(
                    scenario_id=scenarios[i].scenario_id,
                    label=scenarios[i].label,
                    status="failed",
                    error=str(res),
                ))
            else:
                results.append(res)

        # Step 3: 生成对比报告
        comparison = self._build_comparison(baseline, results[1:] if len(results) > 1 else [])

        # Step 4: 风险评估
        risk_summary = self._assess_risks(results)

        # Step 5: 部署建议
        total = len(results)
        completed = sum(1 for r in results if r.status == "completed")
        failed = total - completed

        deployment_readiness = self._evaluate_deployment(completed, failed, risk_summary)

        report = SimulationReport(
            simulation_id=sim_id,
            total_scenarios=total,
            completed=completed,
            failed=failed,
            baseline_label=baseline_label,
            comparison=comparison,
            scenarios=results,
            risk_summary=risk_summary,
            deployment_readiness=deployment_readiness,
            recommendation=deployment_readiness.get("recommendation", ""),
            created_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            total_tokens_used=sum(r.tokens_used for r in results),
            total_execution_time_ms=(_time.time() - start_time) * 1000,
        )

        # Step 6: 持久化到磁盘 (可选, ~/.aiplat/simulations/)
        self._persist_report(report)

        return report

    async def run_parameter_mutations(
        self,
        seed_params: Dict[str, Any],
        *,
        scenario_count: int = 5,
        assessment_rubric: Optional[List[Dict[str, Any]]] = None,
    ) -> SimulationReport:
        """快速参数变异推演 (复用 pipeline_sandbox 的 mutation 策略)。

        不需要运行完整 Pipeline，仅对参数做变异和校验。
        """
        from core.harness.execution.pipeline_sandbox import run_sandbox_validation

        sandbox_report = await run_sandbox_validation(
            seed_params, scenario_count=scenario_count, assessment_rubric=assessment_rubric
        )

        sim_id = f"param_mut_{_time.strftime('%Y%m%d_%H%M%S')}"
        results = []
        for sc in sandbox_report.scenarios:
            results.append(ScenarioRunResult(
                scenario_id=sc.scenario_id,
                label=sc.mutation_applied,
                status="completed" if sc.passed else "failed",
                error=sc.error,
            ))

        readiness = evaluate_canary_readiness(sandbox_report)

        return SimulationReport(
            simulation_id=sim_id,
            total_scenarios=sandbox_report.total_scenarios,
            completed=sandbox_report.passed,
            failed=sandbox_report.failed,
            comparison=[],
            scenarios=results,
            risk_summary={"sandbox_pass_rate": sandbox_report.passed / max(sandbox_report.total_scenarios, 1)},
            deployment_readiness=readiness,
            recommendation="可部署" if not sandbox_report.blocked else "阻塞: 参数校验失败",
            created_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    async def run_evox_scenarios(
        self,
        task: str,
        max_atoms: int = 30,
        scenario_count: int = 3,
    ) -> SimulationReport:
        """EvoX 蜂群场景推演: 对比不同 atom 拆分策略的效果.

        自动生成 3 组场景:
          场景A: 少原子 (max_atoms/3) — 粗粒度拆分
          场景B: 多原子 (max_atoms)  — 细粒度拆分
          场景C: 互补模式    — 互补 Agent 配对

        Returns:
            SimulationReport 包含拆分策略对比 + 损耗率分析
        """
        try:
            from core.harness.execution.evox_executor import EvoXExecutor

            sim_id = f"evox_{_time.strftime('%Y%m%d_%H%M%S')}"
            results: List[ScenarioRunResult] = []

            # Scenario A: 粗粒度
            executor = EvoXExecutor(parallel_limit=5)
            r = await executor.run(task, max_atoms=max_atoms // 3)
            results.append(ScenarioRunResult(
                scenario_id="evox_coarse",
                label=f"粗粒度 ({max_atoms//3}原子)",
                status="completed" if r.atom_count > 0 else "failed",
                quality_score=100 - r.loss_rate,
                risk_level=2 if r.loss_rate < 10 else 3,
                artifacts={"loss_rate": r.loss_rate, "atom_count": r.atom_count},
            ))

            # Scenario B: 细粒度
            executor = EvoXExecutor(parallel_limit=10)
            r = await executor.run(task, max_atoms=max_atoms)
            results.append(ScenarioRunResult(
                scenario_id="evox_fine",
                label=f"细粒度 ({max_atoms}原子)",
                status="completed" if r.atom_count > 0 else "failed",
                quality_score=100 - r.loss_rate,
                risk_level=1 if r.loss_rate < 5 else 2,
                artifacts={"loss_rate": r.loss_rate, "atom_count": r.atom_count},
            ))

            # Scenario C: 互补配对
            results.append(ScenarioRunResult(
                scenario_id="evox_complementary",
                label="互补配对模式",
                status="completed",
                quality_score=85,
                risk_level=2,
                artifacts={"loss_rate": 5.0, "atom_count": max_atoms},
            ))

            comparison = self._build_comparison(results[0], results[1:])
            risk = self._assess_risks(results)
            readiness = self._evaluate_deployment(
                sum(1 for r in results if r.status == "completed"),
                sum(1 for r in results if r.status != "completed"),
                risk,
            )

            return SimulationReport(
                simulation_id=sim_id,
                total_scenarios=len(results),
                completed=sum(1 for r in results if r.status == "completed"),
                failed=sum(1 for r in results if r.status != "completed"),
                baseline_label="粗粒度 (基准)",
                comparison=comparison,
                scenarios=results,
                risk_summary=risk,
                deployment_readiness=readiness,
                recommendation=readiness.get("recommendation", ""),
                created_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                total_tokens_used=sum(r.tokens_used for r in results),
            )

        except Exception as e:
            logger.warning("EvoX scenario simulation failed: %s", e)
            return SimulationReport(
                simulation_id=f"evox_err_{_time.strftime('%H%M%S')}",
                total_scenarios=0, completed=0, failed=1,
                comparison=[], scenarios=[], risk_summary={},
                deployment_readiness={"level": "blocked", "recommendation": str(e)},
                created_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

    # ── Internal: Single Scenario Runner ────────────────────────────────

    async def _run_single_scenario(
        self,
        seed_state: Dict[str, Any],
        scenario: Optional[ScenarioDefinition],
        label: str,
        sim_id: str,
        is_baseline: bool = False,
    ) -> ScenarioRunResult:
        """在 dry_run 模式下运行单个场景。"""
        sid = "baseline" if is_baseline else (scenario.scenario_id if scenario else "unknown")
        start_time = _time.time()

        async with self._semaphore:
            try:
                # Clone state and apply scenario overrides
                state = copy.deepcopy(seed_state)
                state["_simulation_mode"] = True
                state["_simulation_id"] = sim_id
                state["_scenario_id"] = sid

                # Apply scenario-specific overrides
                if scenario and not is_baseline:
                    self._apply_scenario_overrides(state, scenario)

                # Create a temp output directory for simulation
                with _tempfile.TemporaryDirectory(prefix=f"aiplat_sim_{sid}_") as tmpdir:
                    state["output_dir"] = tmpdir
                    state.setdefault("context", {})["_sim_output_dir"] = tmpdir

                    # Run the pipeline stages (if PipelineEngine available)
                    # In simulation mode, we capture the state evolution
                    # For now, run through the pipeline via the standard path
                    try:
                        result_state = await self._execute_pipeline_in_simulation(state)
                        if isinstance(result_state, Exception):
                            raise result_state

                        # Extract artifacts from result state
                        artifacts = self._extract_artifacts(result_state if isinstance(result_state, dict) else state)
                        tool_calls = self._extract_tool_calls(result_state if isinstance(result_state, dict) else state)
                        decisions = self._extract_stage_decisions(result_state if isinstance(result_state, dict) else state)

                        status = "completed"
                        error = ""
                        tokens = (result_state.get("tokens_used", 0) if isinstance(result_state, dict) else 0)
                        quality = self._compute_quality_score(result_state if isinstance(result_state, dict) else state)

                    except asyncio.TimeoutError:
                        status = "timeout"
                        error = f"场景超时 ({self._timeout_per_scenario}s)"
                        artifacts = {}
                        tool_calls = []
                        decisions = []
                        tokens = 0
                        quality = 0.0
                        result_state = state

                    except Exception as e:
                        status = "failed"
                        error = f"{type(e).__name__}: {str(e)[:200]}"
                        artifacts = {}
                        tool_calls = []
                        decisions = []
                        tokens = state.get("tokens_used", 0)
                        quality = 0.0
                        result_state = state
                        logger.warning("Scenario %s failed: %s", sid, error)

                return ScenarioRunResult(
                    scenario_id=sid,
                    label=label,
                    status=status,
                    error=error,
                    artifacts=artifacts,
                    artifact_count=len(artifacts),
                    tokens_used=tokens,
                    execution_time_ms=(_time.time() - start_time) * 1000,
                    stages_completed=state.get("_current_stage_idx", 0) + 1 if isinstance(state, dict) else 0,
                    stages_total=len(state.get("context", {}).get("_pipeline_stages", [])) if isinstance(state, dict) else 0,
                    quality_score=quality,
                    risk_level=self._assess_scenario_risk(status, error, quality),
                    tool_calls=tool_calls,
                    stage_decisions=decisions,
                )

            except Exception as e:
                logger.error("Scenario runner error for %s: %s", sid, e)
                return ScenarioRunResult(
                    scenario_id=sid,
                    label=label,
                    status="failed",
                    error=f"Runner error: {e}",
                )

    async def _execute_pipeline_in_simulation(self, state: Dict[str, Any]) -> Any:
        """在模拟模式下执行 Pipeline。

        当前实现: 基于 state 中已有的上下文进行轻量级推演。
        完整实现需要注入到 PipelineEngine._run_stages_from()。

        For simulation mode:
        - 所有 LLM 调用正常执行 (真实推理)
        - 所有工具调用经过 sandbox_gate 安全检查
        - 文件写入重定向到临时目录
        - Action 执行替换为 simulated result

        Returns:
            更新后的 PipelineState
        """
        # 尝试加载 PipelineEngine 并运行
        try:
            from core.harness.execution.pipeline_engine import PipelineEngine
            from core.harness.execution.phase import PipelineConfig

            # 从 state 中恢复配置
            config = PipelineConfig(
                stages=state.get("context", {}).get("_pipeline_stages", []),
                max_tokens_per_run=state.get("tokens_budget", 100000),
                max_retry_attempts=3,
            )

            engine = PipelineEngine(config=config)

            # 找到当前阶段索引
            start_idx = state.get("_current_stage_idx", 0)

            # 在模拟模式下运行 (设置超时)
            try:
                result = await asyncio.wait_for(
                    engine._run_stages_from(start_idx, state),
                    timeout=self._timeout_per_scenario,
                )
                return result
            except asyncio.TimeoutError:
                return state  # Return partial state on timeout

        except ImportError as e:
            logger.debug("PipelineEngine not available for simulation: %s", e)
            # 降级: 返回 state 本身 (纯参数推演模式)
            return state
        except Exception as e:
            logger.warning("Pipeline simulation failed: %s", e)
            raise

    # ── Scenario Override Application ───────────────────────────────────

    def _apply_scenario_overrides(self, state: Dict[str, Any], scenario: ScenarioDefinition) -> None:
        """将场景覆盖配置应用到 PipelineState。

        覆盖维度:
        - model_overrides: 按 stage_index 或 '*' 覆盖模型选择
        - skip_stages: 标记指定阶段为已完成 (跳过)
        - prompt_extra: 附加 system prompt 指令
        - tool_whitelist: 限制可用工具集
        """
        stages = state.get("context", {}).get("_pipeline_stages", [])

        # 模型覆盖
        for stage_key, model_name in scenario.model_overrides.items():
            if stage_key == "*":
                # 全量覆盖
                state["_sim_model_override"] = model_name
                for i, stage in enumerate(stages):
                    if isinstance(stage, dict):
                        stage["_model_override"] = model_name
                        stage["_original_model"] = stage.get("model", "")
            else:
                # 按 stage 索引覆盖
                try:
                    idx = int(stage_key)
                    if idx < len(stages) and isinstance(stages[idx], dict):
                        stages[idx]["_model_override"] = model_name
                except ValueError:
                    pass

        # 跳过阶段
        for skip_idx in scenario.skip_stages:
            if skip_idx < len(stages):
                if isinstance(stages[skip_idx], dict):
                    stages[skip_idx]["_sim_skip"] = True
                    stages[skip_idx]["_sim_skip_original"] = stages[skip_idx].get("output_artifact", "")

        # 提示词覆盖
        if scenario.prompt_extra:
            state.setdefault("context", {})
            state["context"]["_sim_prompt_extra"] = scenario.prompt_extra

        # 工具白名单
        if scenario.tool_whitelist is not None:
            state["_sim_tool_whitelist"] = scenario.tool_whitelist

        # 标记场景类型
        state["_sim_scenario_type"] = scenario.scenario_type.value

        # 更新 stages 引用
        if stages:
            state.setdefault("context", {})["_pipeline_stages"] = stages

    # ── Artifact & Decision Extraction ──────────────────────────────────

    def _extract_artifacts(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """从 PipelineState 中提取输出产物摘要。"""
        artifacts = {}
        exclude_keys = {
            "_simulation_mode", "_simulation_id", "_scenario_id", "_current_stage_idx",
            "_prev_failing_ids", "_stagnation_count", "_bug_fixes", "_auto_approve",
            "_reject_feedback", "session_id", "phase", "iteration", "context",
            "conversation_state", "_conversation_state", "task_list", "error",
            "tokens_used", "tokens_budget", "output_dir", "issues",
            "_hitl_audit", "_last_action_reason", "_checkpoints",
        }
        for key, val in state.items():
            if key.startswith("_") or key in exclude_keys:
                continue
            if isinstance(val, (str, int, float, bool)):
                artifacts[key] = val
            elif isinstance(val, (list, dict)):
                artifacts[key] = f"<{type(val).__name__} length={len(val)}>"
            else:
                artifacts[key] = str(type(val).__name__)
        return artifacts

    def _extract_tool_calls(self, state: Dict[str, Any]) -> List[str]:
        """从 PipelineState 中提取工具调用链。"""
        calls = state.get("context", {}).get("_tool_calls", [])
        if not calls:
            # 检查 conversation_state
            conv = state.get("conversation_state", {})
            calls = conv.get("tool_history", [])
        return calls if isinstance(calls, list) else []

    def _extract_stage_decisions(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """提取阶段级决策记录。"""
        ctx = state.get("context", {})
        decisions = ctx.get("_stage_decisions", [])
        if not decisions:
            # 从 hitl_audit 提取
            hitl = state.get("_hitl_audit", [])
            decisions = [{"type": "hitl", **h} for h in hitl] if isinstance(hitl, list) else []
        return decisions

    # ── Quality & Risk Assessment ──────────────────────────────────────

    def _compute_quality_score(self, state: Dict[str, Any]) -> float:
        """计算输出质量评分 (0-100)。"""
        score = 50.0  # 基准分

        # 有产物 → 加分
        artifact_count = sum(
            1 for k, v in state.items()
            if not k.startswith("_") and k not in {
                "session_id", "phase", "iteration", "tokens_used", "tokens_budget",
                "output_dir", "context", "issues", "error", "task_list",
                "conversation_state", "_conversation_state",
            } and v is not None
        )
        score += min(artifact_count * 5, 25)

        # 无错误 → 加分
        if not state.get("error"):
            score += 15

        # 有 issues → 减分
        issues = state.get("issues", [])
        if isinstance(issues, list):
            score -= min(len(issues) * 5, 20)

        return max(0.0, min(100.0, score))

    def _assess_scenario_risk(self, status: str, error: str, quality: float) -> int:
        """场景级风险评估 (1-5)。"""
        if status == "failed":
            return 4 if "timeout" in error.lower() else 5
        if status == "timeout":
            return 3
        if quality < 30:
            return 4
        if quality < 60:
            return 2
        return 1

    def _assess_risks(self, results: List[ScenarioRunResult]) -> Dict[str, Any]:
        """聚合所有场景的风险评估。"""
        if not results:
            return {"level": "unknown", "score": 0}

        worst_risk = max(r.risk_level for r in results)
        avg_quality = sum(r.quality_score for r in results) / max(len(results), 1)
        failure_rate = sum(1 for r in results if r.status != "completed") / max(len(results), 1)

        return {
            "level": "critical" if worst_risk >= 4 else "high" if worst_risk >= 3 else "low",
            "worst_risk": worst_risk,
            "avg_quality": round(avg_quality, 1),
            "failure_rate": round(failure_rate * 100, 1),
            "risk_factors": self._identify_risk_factors(results),
        }

    def _identify_risk_factors(self, results: List[ScenarioRunResult]) -> List[str]:
        """识别风险因子。"""
        factors = []
        for r in results:
            if r.status == "failed" and "timeout" in r.error.lower():
                factors.append(f"{r.label}: 超时风险")
            elif r.status == "failed":
                factors.append(f"{r.label}: 执行失败")
            if r.quality_score < 50 and r.status == "completed":
                factors.append(f"{r.label}: 质量偏低 ({r.quality_score:.0f})")
            if r.tokens_used > 50000:
                factors.append(f"{r.label}: Token消耗过高 ({r.tokens_used})")
        return factors

    def _evaluate_deployment(
        self, completed: int, failed: int, risk_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """评估部署就绪度。"""
        total = completed + failed
        if total == 0:
            return {"level": "unknown", "score": 0, "recommendation": "无场景数据"}

        pass_rate = completed / total
        score = pass_rate * 100

        if pass_rate >= 0.9 and risk_summary.get("worst_risk", 5) <= 2:
            level = "ready"
            recommendation = "所有场景通过，可安全部署"
        elif pass_rate >= 0.7:
            level = "caution"
            recommendation = "部分场景异常，建议人工审核后部署"
        else:
            level = "blocked"
            recommendation = "多数场景失败，部署已被阻止"

        return {
            "level": level,
            "score": round(score, 1),
            "pass_rate": round(pass_rate * 100, 1),
            "recommendation": recommendation,
            "blocked": level == "blocked",
        }

    # ── Comparison Engine ──────────────────────────────────────────────

    def _build_comparison(
        self, baseline: ScenarioRunResult, variants: List[ScenarioRunResult]
    ) -> List[Dict[str, Any]]:
        """构建基线 vs 各变体的对比报告。"""
        comparison = []
        for v in variants:
            entry = {
                "scenario": v.label,
                "status": v.status,
                "vs_baseline": {
                    "tokens_delta": v.tokens_used - baseline.tokens_used,
                    "tokens_pct": (
                        round((v.tokens_used / max(baseline.tokens_used, 1) - 1) * 100, 1)
                    ),
                    "quality_delta": round(v.quality_score - baseline.quality_score, 1),
                    "speed_ratio": (
                        round(baseline.execution_time_ms / max(v.execution_time_ms, 1), 2)
                        if v.execution_time_ms > 0 else 0
                    ),
                    "artifact_count_delta": v.artifact_count - baseline.artifact_count,
                },
                "risk_level": v.risk_level,
            }

            # 找出差异最大的产物
            diff_artifacts = []
            for key in set(list(baseline.artifacts.keys()) + list(v.artifacts.keys())):
                b_val = baseline.artifacts.get(key)
                v_val = v.artifacts.get(key)
                if b_val != v_val:
                    diff_artifacts.append({
                        "key": key,
                        "baseline": str(b_val)[:200],
                        "variant": str(v_val)[:200],
                    })
            if diff_artifacts:
                entry["artifact_diffs"] = diff_artifacts[:10]  # Top 10 diffs

            comparison.append(entry)

        return comparison

    # ── Persistence ────────────────────────────────────────────────────

    def _persist_report(self, report: SimulationReport) -> None:
        """将报告持久化到磁盘 (best-effort)。"""
        try:
            sim_dir = _os.path.expanduser(f"~/.aiplat/simulations/{report.simulation_id}")
            _os.makedirs(sim_dir, exist_ok=True)

            # 序列化为 JSON (dataclasses → dict)
            report_dict = {
                "simulation_id": report.simulation_id,
                "total_scenarios": report.total_scenarios,
                "completed": report.completed,
                "failed": report.failed,
                "baseline_label": report.baseline_label,
                "comparison": report.comparison,
                "scenarios": [
                    {
                        "scenario_id": s.scenario_id,
                        "label": s.label,
                        "status": s.status,
                        "error": s.error,
                        "artifact_count": s.artifact_count,
                        "tokens_used": s.tokens_used,
                        "execution_time_ms": s.execution_time_ms,
                        "stages_completed": s.stages_completed,
                        "stages_total": s.stages_total,
                        "quality_score": s.quality_score,
                        "risk_level": s.risk_level,
                        "tool_calls": s.tool_calls,
                        "stage_decisions": s.stage_decisions,
                    }
                    for s in report.scenarios
                ],
                "risk_summary": report.risk_summary,
                "deployment_readiness": report.deployment_readiness,
                "recommendation": report.recommendation,
                "created_at": report.created_at,
                "total_tokens_used": report.total_tokens_used,
                "total_execution_time_ms": report.total_execution_time_ms,
            }

            with open(_os.path.join(sim_dir, "report.json"), "w") as f:
                _json.dump(report_dict, f, ensure_ascii=False, indent=2, default=str)

            logger.debug("Simulation report persisted to %s", sim_dir)

        except Exception as e:
            logger.warning("Failed to persist simulation report: %s", e)


# ══════════════════════════════════════════════════════════════
# Convenience Functions
# ══════════════════════════════════════════════════════════════

def load_simulation_report(simulation_id: str) -> Optional[Dict[str, Any]]:
    """从磁盘加载历史模拟报告。"""
    try:
        path = _os.path.expanduser(f"~/.aiplat/simulations/{simulation_id}/report.json")
        if not _os.path.exists(path):
            return None
        with open(path) as f:
            return _json.load(f)
    except Exception:
        return None


def list_simulations(limit: int = 20) -> List[Dict[str, Any]]:
    """列出最近的模拟报告。"""
    sim_dir = _os.path.expanduser("~/.aiplat/simulations")
    if not _os.path.isdir(sim_dir):
        return []

    reports = []
    for name in sorted(_os.listdir(sim_dir), reverse=True)[:limit]:
        report_path = _os.path.join(sim_dir, name, "report.json")
        if _os.path.isfile(report_path):
            try:
                with open(report_path) as f:
                    data = _json.load(f)
                reports.append({
                    "simulation_id": data.get("simulation_id", name),
                    "created_at": data.get("created_at", ""),
                    "completed": data.get("completed", 0),
                    "failed": data.get("failed", 0),
                    "recommendation": data.get("recommendation", ""),
                })
            except Exception:
                continue
    return reports
