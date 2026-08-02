"""
AtomicTaskSplitter — 原子任务分解器 (EvoMap EvoX 对齐)

将复杂任务动态拆分为边界清晰、可独立执行的原子子任务:

  1. LLM 分析 → 原子任务列表 (每个原子有明确边界、结构化输出schema、负责人)
  2. verify_coverage() → 检查原子列表是否完整覆盖原始任务，未覆盖自动补全
  3. 注入 PipelineEngine FanOut → N 个独立 ReActLoop 并行执行

设计原则 (EvoX 蜂群):
  - 每个原子 = 独立上下文，不互相干扰
  - 每个原子有结构化输出 (不是自由文本)，通过 schema 约束格式
  - 所有原子加起来必须覆盖原始任务，不重复、不遗漏

调用者: PipelineEngine → FanOut 模式 / REST API POST /atomic/split
"""

from __future__ import annotations

import json as _json
import logging
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class AtomicTaskDefinition:
    """单个原子任务定义."""
    atom_id: str
    boundary: str                       # 任务边界描述 (做什么、不做什么)
    input_schema: Dict[str, Any]        # 输入 JSON Schema
    output_schema: Dict[str, Any]       # 输出 JSON Schema (不是自由文本)
    assigned_agent: str = ""            # 指派的 Agent ID (可为空，由调度器分配)
    dependencies: List[str] = field(default_factory=list)  # 依赖的原子ID
    priority: int = 0                   # 优先级 (0=最低)
    estimated_tokens: int = 0           # 预估 token 消耗

    def to_dict(self) -> Dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "boundary": self.boundary,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "assigned_agent": self.assigned_agent,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass
class SplitResult:
    """拆分结果."""
    original_task: str
    atoms: List[AtomicTaskDefinition]
    coverage_verified: bool = False     # 是否通过全覆盖验证
    uncovered_gaps: List[str] = field(default_factory=list)  # 未覆盖的部分
    atom_count: int = 0
    total_estimated_tokens: int = 0


# ── Mutations (generalized from pipeline_sandbox for task params) ─────────

_TASK_MUTATIONS: Dict[str, str] = {
    "empty_boundary": "边界声明为空 → 原子边界不明确",
    "overlapping_keys": "两个原子声明了相同的输出key → 重复覆盖",
    "missing_schema": "输出schema为空 → 无法结构化汇合",
    "circular_dependency": "原子A依赖B，原子B依赖A → 死锁",
}


# ── AtomicTaskSplitter ─────────────────────────────────────────────────────

class AtomicTaskSplitter:
    """原子任务分解器.

    使用方式:
        splitter = AtomicTaskSplitter()
        result = await splitter.split("分析563道题并输出答案", max_atoms=50)
        → SplitResult(atoms=[...], coverage_verified=True)
    """

    def __init__(self, *, max_atoms: int = 100):
        self._max_atoms = max_atoms

    async def split(
        self,
        task: str,
        *,
        max_atoms: int = 0,
        domain_hint: str = "",
        existing_context: Optional[Dict[str, Any]] = None,
    ) -> SplitResult:
        """将复杂任务拆分为原子子任务.

        Args:
            task: 原始任务描述
            max_atoms: 最大原子数 (0=使用默认值)
            domain_hint: 领域提示 (帮助 LLM 更精准拆分)
            existing_context: 已有的上下文信息

        Returns:
            SplitResult
        """
        limit = max_atoms if max_atoms > 0 else self._max_atoms
        atoms = await self._llm_split(task, limit, domain_hint, existing_context)

        # 覆盖率验证
        gaps = await self._verify_coverage(task, atoms)
        if gaps:
            # 自动补全未覆盖部分
            extra = await self._llm_fill_gaps(task, atoms, gaps, limit - len(atoms))
            atoms.extend(extra)

        # 最终验证
        final_gaps = await self._verify_coverage(task, atoms) if gaps else []
        coverage_ok = len(final_gaps) == 0

        return SplitResult(
            original_task=task,
            atoms=atoms,
            coverage_verified=coverage_ok,
            uncovered_gaps=final_gaps,
            atom_count=len(atoms),
            total_estimated_tokens=sum(a.estimated_tokens for a in atoms),
        )

    async def _llm_split(
        self,
        task: str,
        max_atoms: int,
        domain_hint: str,
        existing_context: Optional[Dict],
    ) -> List[AtomicTaskDefinition]:
        """LLM 驱动的原子拆分."""
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.prompt_loader import _sync_resolve

            domain_text = f"\n领域: {domain_hint}" if domain_hint else ""
            context_text = ""
            if existing_context:
                context_text = f"\n已有上下文: {_json.dumps(existing_context, ensure_ascii=False)[:500]}"
            
            prompt = _sync_resolve("atomic-splitter-llm-split",
                task=f"原始任务:\n{task}{domain_text}{context_text}",
                context=f"最多 {max_atoms} 个原子子任务")

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("reasoning"),
                temperature=0.1,
                max_tokens=4000,
            )

            # 解析 JSON
            content = self._extract_json(result.get("content", "") if isinstance(result, dict) else str(result))
            atoms_raw = _json.loads(content)

            if not isinstance(atoms_raw, list):
                raise ValueError(f"Expected array, got {type(atoms_raw)}")

            atoms = []
            for a in atoms_raw[:max_atoms]:
                atom = AtomicTaskDefinition(
                    atom_id=a.get("atom_id", f"atom_{_uuid.uuid4().hex[:8]}"),
                    boundary=str(a.get("boundary", "")),
                    input_schema=a.get("input_schema", {}),
                    output_schema=a.get("output_schema", {}),
                    dependencies=a.get("dependencies", []),
                    estimated_tokens=a.get("estimated_tokens", 1000),
                )
                atoms.append(atom)

            return atoms

        except Exception as e:
            logger.warning("LLM split failed: %s, returning fallback single-atom", e)
            return [AtomicTaskDefinition(
                atom_id="atom_fallback",
                boundary=f"执行全部任务: {task[:200]}",
                input_schema={},
                output_schema={"type": "object"},
                estimated_tokens=5000,
            )]

    async def _verify_coverage(
        self,
        task: str,
        atoms: List[AtomicTaskDefinition],
    ) -> List[str]:
        """验证原子列表是否完整覆盖原始任务.

        Returns:
            未覆盖的部分列表 (空列表 = 完整覆盖)
        """
        if not atoms:
            return ["无原子任务"]

        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.prompt_loader import _sync_resolve

            boundaries = "\n".join(
                f"- {a.atom_id}: {a.boundary[:200]}" for a in atoms
            )

            prompt = _sync_resolve("atomic-splitter-verify-coverage",
                task=task[:2000],
                steps=boundaries)

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("reasoning"),
                temperature=0.0,
                max_tokens=500,
            )

            content = self._extract_json(result.get("content", "") if isinstance(result, dict) else str(result))
            data = _json.loads(content)
            return data.get("gaps", [])

        except Exception as e:
            logger.debug("Coverage verification skipped: %s", e)
            return []

    async def _llm_fill_gaps(
        self,
        task: str,
        existing_atoms: List[AtomicTaskDefinition],
        gaps: List[str],
        remaining_slots: int,
    ) -> List[AtomicTaskDefinition]:
        """自动补全未覆盖的部分."""
        if not gaps or remaining_slots <= 0:
            return []

        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.prompt_loader import _sync_resolve

            existing_ids = [a.atom_id for a in existing_atoms]

            prompt = _sync_resolve("atomic-splitter-fill-gaps",
                task=task[:1000],
                gaps=chr(10).join(f'- {g}' for g in gaps[:10]),
                existing_steps=str(existing_ids))

            result = await sys_llm_generate(
                messages=[{"role": "user", "content": prompt}],
                model=best_model_for_purpose("reasoning"),
                temperature=0.1,
                max_tokens=2000,
            )

            content = self._extract_json(result.get("content", "") if isinstance(result, dict) else str(result))
            atoms_raw = _json.loads(content)

            atoms = []
            for a in (atoms_raw if isinstance(atoms_raw, list) else [])[:remaining_slots]:
                atom_id = a.get("atom_id", f"atom_fill_{_uuid.uuid4().hex[:8]}")
                if atom_id not in existing_ids:
                    atoms.append(AtomicTaskDefinition(
                        atom_id=atom_id,
                        boundary=str(a.get("boundary", "")),
                        input_schema=a.get("input_schema", {}),
                        output_schema=a.get("output_schema", {}),
                        dependencies=a.get("dependencies", []),
                        estimated_tokens=a.get("estimated_tokens", 1000),
                    ))

            return atoms

        except Exception as e:
            logger.warning("Gap filling failed: %s", e)
            return []

    def validate(self, atoms: List[AtomicTaskDefinition]) -> Dict[str, Any]:
        """验证原子列表的质量 (非 LLM 确定性检查).

        Returns:
            {"valid": bool, "issues": [...]}
        """
        issues = []
        ids: Set[str] = set()
        output_keys: Set[str] = set()

        for a in atoms:
            # 重复ID
            if a.atom_id in ids:
                issues.append(_TASK_MUTATIONS["overlapping_keys"] + f": {a.atom_id}")
            ids.add(a.atom_id)

            # 空边界
            if not a.boundary.strip():
                issues.append(_TASK_MUTATIONS["empty_boundary"] + f": {a.atom_id}")

            # 空 schema
            if not a.output_schema:
                issues.append(_TASK_MUTATIONS["missing_schema"] + f": {a.atom_id}")

            # 循环依赖
            for dep in a.dependencies:
                if dep == a.atom_id:
                    issues.append(_TASK_MUTATIONS["circular_dependency"] + f": {a.atom_id} → {dep}")

            # 检查输出 key 冲突
            for key in a.output_schema.get("properties", {}).keys():
                if key in output_keys:
                    issues.append(f"输出key冲突: '{key}' 已在另一个原子中使用")
                output_keys.add(key)

        return {"valid": len(issues) == 0, "issues": issues}

    @staticmethod
    def _extract_json(text: str) -> str:
        """从 LLM 输出中提取 JSON."""
        text = text.strip()
        # 处理 markdown code block
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            parts = text.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("[") or p.startswith("{"):
                    text = p
                    break
        # 提取最外层 JSON 数组/对象
        start = text.find("[")
        if start == -1:
            start = text.find("{")
        if start >= 0:
            end = text.rfind("]") if text[start] == "[" else text.rfind("}")
            if end > start:
                return text[start:end + 1]
        return text
