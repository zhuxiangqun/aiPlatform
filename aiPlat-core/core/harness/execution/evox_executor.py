"""
EvoXExecutor — EvoX 蜂群执行器 (Wire AtomicTaskSplitter → PipelineEngine → Collector)

将三个 EvoX 阶段串联为完整的蜂群执行流水线:

  1. AtomicTaskSplitter.split() → 原子任务列表
  2. PipelineEngine FanOut → N 个独立 StageRunner 并行执行
  3. ProgrammaticCollector.collect_and_detect() → 结构化汇合 + 损耗检测

调用者: REST API /evo/execute / FDE 工作台
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.harness.execution.atomic_splitter import AtomicTaskSplitter, SplitResult, AtomicTaskDefinition
from core.harness.execution.programmatic_collector import ProgrammaticCollector, CollectResult, LossReport

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class EvoXResult:
    """EvoX 蜂群执行结果."""
    task: str
    atom_count: int
    coverage_verified: bool

    # 执行阶段
    atoms_executed: int = 0
    atoms_failed: int = 0

    # 汇合阶段
    collected_count: int = 0
    missed_count: int = 0

    # 损耗分析
    total_correct_in_atoms: int = 0
    total_correct_in_final: int = 0
    loss_count: int = 0
    loss_rate: float = 0.0
    retention_rate: float = 100.0
    loss_root_causes: List[str] = field(default_factory=list)

    # 汇总
    summary: str = ""
    total_time_ms: float = 0.0
    total_tokens: int = 0


# ── EvoXExecutor ──────────────────────────────────────────────────────────

class EvoXExecutor:
    """EvoX 蜂群执行器.

    使用方式:
        executor = EvoXExecutor()
        result = await executor.run(
            task="分析563道题并输出所有答案",
            max_atoms=50,
            parallel_limit=10,
        )
    """

    def __init__(self, *, max_atoms_default: int = 50, parallel_limit: int = 10):
        self._splitter = AtomicTaskSplitter(max_atoms=max_atoms_default)
        self._collector = ProgrammaticCollector()
        self._parallel_limit = parallel_limit

    async def run(
        self,
        task: str,
        *,
        max_atoms: int = 0,
        domain_hint: str = "",
        existing_state: Optional[Dict[str, Any]] = None,
    ) -> EvoXResult:
        """完整 EvoX 蜂群流水线.

        步骤:
          1. 原子拆分
          2. 并行执行 (FanOut)
          3. 程序化汇合
          4. 损耗检测

        Args:
            task: 原始任务描述
            max_atoms: 最大原子数 (0=使用默认值)
            domain_hint: 领域提示
            existing_state: 已有的 PipelineState (如有)

        Returns:
            EvoXResult
        """
        start_time = _time.time()

        # Step 1: 原子拆分
        logger.info("EvoX Step 1: Splitting task into atoms...")
        split_result = await self._splitter.split(
            task, max_atoms=max_atoms or self._splitter._max_atoms,
            domain_hint=domain_hint,
        )

        if not split_result.atoms:
            return EvoXResult(
                task=task,
                atom_count=0,
                coverage_verified=False,
                summary="拆分失败: 无原子任务生成",
            )

        # Step 2: 并行执行 (通过 PipelineEngine FanOut)
        logger.info("EvoX Step 2: Executing %d atoms in parallel (limit=%d)...",
                     split_result.atom_count, self._parallel_limit)

        state = await self._execute_atoms_in_parallel(
            split_result.atoms,
            existing_state or {},
        )

        # Step 3+4: 收集 + 损耗检测
        logger.info("EvoX Step 3+4: Collecting and detecting loss...")
        collect_result, loss_report = self._collector.collect_and_detect(
            state,
            [a.to_dict() for a in split_result.atoms],
            state.get("_final_output"),
        )

        # Step 3.5: Template rendering (if output_template specified)
        template_output = None
        output_template = state.get("_output_template", "")
        if output_template:
            try:
                from core.harness.document.template_engine import TemplateRenderer
                renderer = TemplateRenderer()
                template_output = renderer.render(
                    output_template,
                    collect_result.merged_output if collect_result else {},
                )
                logger.info("Template rendered: %s", template_output.get("path", ""))
            except Exception as e:
                logger.debug("Template rendering skipped: %s", e)

        elapsed = (_time.time() - start_time) * 1000

        return EvoXResult(
            task=task,
            atom_count=split_result.atom_count,
            coverage_verified=split_result.coverage_verified,
            atoms_executed=collect_result.collected_atoms,
            atoms_failed=len(collect_result.missed_atoms),
            collected_count=collect_result.collected_atoms,
            missed_count=len(collect_result.missed_atoms),
            total_correct_in_atoms=loss_report.total_correct_in_atoms if loss_report else 0,
            total_correct_in_final=loss_report.total_correct_in_final if loss_report else 0,
            loss_count=loss_report.loss_count if loss_report else 0,
            loss_rate=loss_report.loss_rate if loss_report else 0.0,
            retention_rate=loss_report.retention_rate if loss_report else 100.0,
            loss_root_causes=loss_report.root_causes if loss_report else [],
            summary=(
                f"拆分 {split_result.atom_count} 原子, 收集 {collect_result.collected_atoms}, "
                f"损耗 {loss_report.loss_rate if loss_report else 0}%"
            ),
            total_time_ms=elapsed,
            total_tokens=state.get("tokens_used", 0),
        )

    async def _execute_atoms_in_parallel(
        self,
        atoms: List[AtomicTaskDefinition],
        base_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """并行执行原子任务.

        为每个原子创建独立的 PipelineStage，通过 Semaphore 限制并发数.
        """
        semaphore = asyncio.Semaphore(self._parallel_limit)
        state = dict(base_state)
        state.setdefault("_atom_executions", {})
        total_tokens = state.get("tokens_used", 0)

        async def _run_atom(atom: AtomicTaskDefinition) -> Dict[str, Any]:
            async with semaphore:
                try:
                    from core.harness.utils.model_injection import best_model_for_purpose
                    from core.harness.syscalls.llm import sys_llm_generate

                    # 为每个原子构建独立 prompt
                    prompt = self._build_atom_prompt(atom, base_state)

                    result = await sys_llm_generate(
                        messages=[{"role": "user", "content": prompt}],
                        model=best_model_for_purpose("code_gen"),
                        temperature=0.2,
                        max_tokens=atom.estimated_tokens or 2000,
                    )
                    content = result.get("content", "") if isinstance(result, dict) else str(result)

                    # 尝试解析结构化输出
                    output = self._parse_atom_output(content, atom)
                    return {atom.atom_id: output}

                except Exception as e:
                    logger.warning("Atom %s failed: %s", atom.atom_id, e)
                    return {atom.atom_id: {"error": str(e)[:200]}}

        # 并行执行所有原子
        tasks = [_run_atom(atom) for atom in atoms]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 汇总结果到 state
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                atom_id = atoms[i].atom_id if i < len(atoms) else f"atom_{i}"
                state["_atom_executions"][atom_id] = {"error": str(result)}
            elif isinstance(result, dict):
                for key, val in result.items():
                    state[key] = val
                    state["_atom_executions"][key] = val

        # 计算总 token (best-effort)
        for r in results:
            if isinstance(r, dict):
                for val in r.values():
                    if isinstance(val, dict) and "tokens" in val:
                        total_tokens += val.get("tokens", 0)

        state["tokens_used"] = total_tokens
        return state

    def _build_atom_prompt(
        self,
        atom: AtomicTaskDefinition,
        base_state: Dict[str, Any],
    ) -> str:
        """为原子任务构建独立的执行 prompt."""
        schema_str = _json.dumps(atom.output_schema, ensure_ascii=False) if atom.output_schema else ""
        input_str = _json.dumps(atom.input_schema, ensure_ascii=False) if atom.input_schema else ""

        return f"""执行以下原子任务。

任务边界:
{atom.boundary}

输入结构:
{input_str or "无特定输入"}

输出要求:
请严格按照以下 JSON Schema 输出结果:
{schema_str or '{{"result": "string"}}'}

注意:
- 只处理你边界内的任务
- 输出必须是有效的 JSON，不要添加额外文字
- 如果任务超出你的边界，返回 {{"skipped": true, "reason": "超出边界"}}
"""

    def _parse_atom_output(self, content: str, atom: AtomicTaskDefinition) -> Dict[str, Any]:
        """解析原子输出为结构化数据."""
        # 提取 JSON
        try:
            # 处理 markdown code block
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                parts = content.split("```")
                for p in parts:
                    p = p.strip()
                    if p.startswith("{") or p.startswith("["):
                        content = p
                        break

            start = content.find("{")
            if start >= 0:
                end = content.rfind("}")
                if end > start:
                    return _json.loads(content[start:end + 1])

        except Exception:
            pass

        return {"raw_output": content[:1000]}
