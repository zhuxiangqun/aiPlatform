"""
ProgrammaticCollector — 程序化结果汇合 + 损耗检测 (EvoMap EvoX 对齐)

绕过 LLM 转述，直接从 PipelineState 按 key 结构化收集原子任务输出。
对比各原子正确输出 vs 最终汇总，计算信息损耗率。

设计原则 (EvoX):
  - Agent 负责解题，应用程序负责收件
  - 结构化输出写入固定位置 (state[output_artifact])
  - 程序按 key 直接收集，正确答案不需要被另一个 LLM 重新读懂
  - 损耗检测: 对比原子正确结果 → 汇总结果，计算损耗率

调用者: PipelineEngine → collector stage / REST API
"""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────────────────────────

@dataclass
class CollectResult:
    """汇合结果."""
    total_atoms: int
    collected_atoms: int
    missed_atoms: List[str] = field(default_factory=list)  # 未产出结果的原子
    merged_output: Dict[str, Any] = field(default_factory=dict)  # 合并后的结构化输出
    merged_summary: str = ""           # 可读摘要


@dataclass
class LossReport:
    """损耗分析报告."""
    total_correct_in_atoms: int        # 原子阶段正确数
    total_correct_in_final: int        # 最终汇总正确数
    loss_count: int                    # 丢失数
    loss_rate: float                   # 损耗率 (%)
    loss_details: List[Dict[str, Any]] = field(default_factory=list)  # 每个丢失项的详情
    root_causes: List[str] = field(default_factory=list)  # 根因分析
    retention_rate: float = 0.0        # 保留率 (%)


# ── ProgrammaticCollector ──────────────────────────────────────────────────

class ProgrammaticCollector:
    """程序化结果汇合.

    使用方式:
        collector = ProgrammaticCollector()
        result = collector.collect(state, atom_definitions)
        loss = collector.detect_loss(atom_outputs, final_output, atom_defs)
    """

    def collect(
        self,
        state: Dict[str, Any],
        atom_definitions: List[Dict[str, Any]],
        *,
        merge_strategy: str = "by_schema",
    ) -> CollectResult:
        """从 PipelineState 中按 key 结构化收集所有原子输出.

        Args:
            state: PipelineState (包含各原子的 output_artifact)
            atom_definitions: 原子任务定义列表 (来自 AtomicTaskSplitter)
            merge_strategy: 合并策略 — "by_schema" (按schema对齐) | "concat" (简单拼接)

        Returns:
            CollectResult
        """
        collected = {}
        missed = []

        for atom_def in atom_definitions:
            atom_id = atom_def.get("atom_id", "")
            output_key = atom_def.get("output_artifact", atom_id)
            output_schema = atom_def.get("output_schema", {})

            # 直接从 state 读取 (不经过 LLM)
            atom_output = state.get(output_key)

            if atom_output is None:
                # Try alternate keys
                for alt_key in [f"atom_{atom_id}", atom_id, f"output_{atom_id}"]:
                    atom_output = state.get(alt_key)
                    if atom_output is not None:
                        break

            if atom_output is None:
                missed.append(atom_id)
                continue

            # 按 schema 验证和提取
            extracted = self._extract_by_schema(atom_output, output_schema, atom_id)
            if extracted:
                collected[atom_id] = extracted

        # 合并所有收集的结果
        merged = self._merge_outputs(collected, atom_definitions, merge_strategy)

        return CollectResult(
            total_atoms=len(atom_definitions),
            collected_atoms=len(collected),
            missed_atoms=missed,
            merged_output=merged,
            merged_summary=f"收集 {len(collected)}/{len(atom_definitions)} 个原子 (缺失 {len(missed)})",
        )

    def _extract_by_schema(
        self,
        atom_output: Any,
        output_schema: Dict[str, Any],
        atom_id: str,
    ) -> Optional[Dict[str, Any]]:
        """按输出 schema 提取结构化数据."""
        # 如果已经是 dict，直接按 schema 字段提取
        if isinstance(atom_output, dict):
            props = output_schema.get("properties", {})
            if not props:
                return {atom_id: atom_output}

            result = {}
            for key in props:
                if key in atom_output:
                    result[key] = atom_output[key]
            return {atom_id: result} if result else {atom_id: atom_output}

        # 字符串类型 → 尝试解析 JSON
        if isinstance(atom_output, str):
            try:
                data = _json.loads(atom_output)
                return self._extract_by_schema(data, output_schema, atom_id)
            except Exception:
                return {atom_id: {"raw_output": atom_output[:500]}}

        return {atom_id: {"output": str(atom_output)[:500]}}

    def _merge_outputs(
        self,
        collected: Dict[str, Dict[str, Any]],
        atom_definitions: List[Dict[str, Any]],
        strategy: str,
    ) -> Dict[str, Any]:
        """合并各原子输出."""
        if strategy == "concat":
            return {"atoms": collected, "total": len(collected)}

        # By schema: 按原子ID分组，尝试同 schema 对齐
        merged: Dict[str, Any] = {"atoms": {}, "summary": {}}

        for atom_id, data in collected.items():
            merged["atoms"][atom_id] = data

            # 提取数值型结果用于汇总
            for key, val in data.items():
                if isinstance(val, (int, float)):
                    merged["summary"].setdefault(key, 0)
                    merged["summary"][key] += val
                elif isinstance(val, dict) and "correct_count" in val:
                    merged["summary"].setdefault("correct_count", 0)
                    merged["summary"]["correct_count"] += val["correct_count"]

        merged["summary"]["atoms_collected"] = len(collected)
        return merged

    def detect_loss(
        self,
        atom_outputs: Dict[str, Any],
        final_output: Dict[str, Any],
        atom_definitions: List[Dict[str, Any]],
    ) -> LossReport:
        """检测汇总过程中的信息损耗.

        对比各原子输出中的正确结果 vs 最终汇总输出中的正确结果.

        Args:
            atom_outputs: 各原子的结构化输出 {atom_id: {result...}}
            final_output: 最终汇总输出 (可能经过 LLM 汇总)
            atom_definitions: 原子任务定义

        Returns:
            LossReport
        """
        total_correct = 0
        correct_items: Set[str] = set()
        loss_details: List[Dict[str, Any]] = []

        # Step 1: 统计各原子中的正确结果
        for atom_id, data in atom_outputs.items():
            if isinstance(data, dict):
                # 查找正确标记
                for key in ["correct_count", "passed", "success_count"]:
                    if key in data:
                        val = data[key]
                        if isinstance(val, (int, float)) and val > 0:
                            total_correct += int(val)
                            correct_items.add(atom_id)

                # 查找答案字典
                answers = data.get("answers", {})
                if isinstance(answers, dict):
                    for qid, answer in answers.items():
                        correct_items.add(f"{atom_id}:{qid}")

        # Step 2: 统计最终汇总中的正确结果
        final_correct = 0
        if isinstance(final_output, dict):
            for key in ["correct_count", "passed", "total_correct"]:
                if key in final_output:
                    val = final_output[key]
                    if isinstance(val, (int, float)):
                        final_correct = int(val)
                        break

            # 也检查 answers
            final_answers = final_output.get("answers", {})
            if isinstance(final_answers, dict):
                final_correct = max(final_correct, len(final_answers))

        # Step 3: 对比损耗
        loss_count = max(0, total_correct - final_correct)
        loss_rate = (loss_count / max(total_correct, 1)) * 100

        # Step 4: 根因分析
        root_causes = []
        if loss_count > 0:
            if final_correct < total_correct and final_output:
                root_causes.append(
                    f"汇总环节信息丢失: 原子阶段 {total_correct} 正确 → 汇总后仅保留 {final_correct} 正确"
                )
            if isinstance(final_output, str) and len(str(final_output)) < 200:
                root_causes.append("汇总输出过于简洁，可能丢失了细节")

            # 检查是否有遗漏的原子
            missed = [d.get("atom_id", "") for d in atom_definitions
                      if d.get("atom_id", "") not in atom_outputs]
            if missed:
                root_causes.append(f"{len(missed)} 个原子未产出结果或结果未被收集")

        return LossReport(
            total_correct_in_atoms=total_correct,
            total_correct_in_final=final_correct,
            loss_count=loss_count,
            loss_rate=round(loss_rate, 1),
            loss_details=loss_details[:50],
            root_causes=root_causes,
            retention_rate=round(100 - loss_rate, 1),
        )

    def collect_and_detect(
        self,
        state: Dict[str, Any],
        atom_definitions: List[Dict[str, Any]],
        final_output: Optional[Dict[str, Any]] = None,
    ) -> Tuple[CollectResult, Optional[LossReport]]:
        """一键执行: 收集 + 损耗检测.

        Returns:
            (CollectResult, Optional[LossReport])
        """
        collect_result = self.collect(state, atom_definitions)

        loss_report = None
        if final_output and collect_result.collected_atoms > 0:
            loss_report = self.detect_loss(
                collect_result.merged_output.get("atoms", {}),
                final_output,
                atom_definitions,
            )

        # 如果有损耗，写入 lineage_decisions
        if loss_report and loss_report.loss_count > 0:
            self._write_loss_to_lineage(state, loss_report)

        return collect_result, loss_report

    def _write_loss_to_lineage(
        self,
        state: Dict[str, Any],
        loss_report: LossReport,
    ) -> None:
        """将损耗分析写入 Decision Lineage (best-effort)."""
        try:
            from core.harness.infrastructure.lineage_store import LineageStore, DecisionRecord

            run_id = state.get("session_id", "") or state.get("_simulation_id", "unknown")
            if not run_id:
                return

            store = LineageStore.get()
            record = DecisionRecord(
                run_id=run_id,
                decision_type="loss_detection",
                chosen_option="structured_collect",
                choice_reasoning=(
                    f"损耗分析: {loss_report.total_correct_in_atoms}→{loss_report.total_correct_in_final} "
                    f"(丢失 {loss_report.loss_count}, 保留率 {loss_report.retention_rate}%). "
                    f"根因: {'; '.join(loss_report.root_causes[:3])}"
                ),
                outcome_status="logged",
                outcome_summary=f"Loss rate: {loss_report.loss_rate}%",
            )
            store.insert(record)

        except Exception as e:
            logger.debug("Loss lineage write skipped: %s", e)
