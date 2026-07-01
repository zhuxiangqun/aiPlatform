"""
TraceVisualizer — Agent 决策痕迹 → 开发者可读格式 (Andrew Ng 三层 Loop P2)

将 DynamicRouter 运行时产生的 _dynamic_trace 翻译为:
  1. 决策链: 每一步选了谁、Supervisor 的推理依据
  2. 犹豫点: Agent 重新考虑时的不确定信号
  3. 异常点: 同一 Agent 被重复调用 / 跳过 / 超时
  4. 效率摘要: 总步数、重复率、路径选择多样性

输出格式: 开发者直接可用的文本 + 结构化数据，帮助理解 Agent 行为、
定位 Spec 需要修正的地方。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("aiplat.trace_visualizer")


@dataclass
class TraceStep:
    step: int
    agent: str
    reasoning: str
    decision: str
    is_hesitation: bool = False      # 推理中出现"考虑"、"可能"、"或" 等不确定词
    is_repeat: bool = False          # 同一 Agent 在前几步已被调用过
    outcome: str = ""                # ok / timeout / error


@dataclass
class TraceSummary:
    spec_id: str
    total_steps: int
    unique_agents: List[str]
    agent_call_order: List[str]      # 实际调用顺序
    repeat_count: int                 # 重复调用次数
    hesitation_count: int             # 犹豫步数
    max_repeat_agent: str = ""        # 被重复调用最多的 Agent
    steps: List[TraceStep] = field(default_factory=list)
    anomaly_warnings: List[str] = field(default_factory=list)
    spec_suggestions: List[str] = field(default_factory=list)


class TraceVisualizer:
    """原始 trace → 开发者可读分析。

    Usage:
        viz = TraceVisualizer()
        summary = viz.analyze(trace_data, spec_id="my-agent", stage_count=5)
        # summary.anomaly_warnings → ["architect 被调用 3 次，可能是 task 拆分过细"]
        # summary.spec_suggestions → ["建议在 Stage 2 增加 output_artifact 约束"]
    """

    # 中文犹豫词 → likelihood 评分
    HESITATION_PATTERNS = [
        ("考虑", 0.5), ("可能", 0.4), ("不确定", 0.7),
        ("或者", 0.3), ("暂时", 0.3), ("尝试", 0.4),
        ("maybe", 0.4), ("perhaps", 0.4), ("unclear", 0.6),
        ("alternatively", 0.4),
    ]

    def analyze(
        self,
        trace: List[Dict[str, Any]],
        *,
        spec_id: str = "",
        stage_count: int = 0,
        goal: str = "",
    ) -> TraceSummary:
        steps = self._parse_steps(trace)
        unique = list(dict.fromkeys(s.agent for s in steps if s.agent))
        repeats = [s for s in steps if s.is_repeat]
        hesitations = [s for s in steps if s.is_hesitation]
        max_repeat = self._most_repeated(steps)

        summary = TraceSummary(
            spec_id=spec_id,
            total_steps=len(steps),
            unique_agents=unique,
            agent_call_order=[s.agent for s in steps if s.agent],
            repeat_count=len(repeats),
            hesitation_count=len(hesitations),
            max_repeat_agent=max_repeat,
            steps=steps,
        )

        # 异常检测
        summary.anomaly_warnings = self._detect_anomalies(steps, stage_count)
        # Spec 调整建议
        summary.spec_suggestions = self._suggest_spec_changes(steps, stage_count, goal)

        return summary

    def _parse_steps(self, trace: List[Dict[str, Any]]) -> List[TraceStep]:
        seen: Dict[str, int] = {}  # agent → first_step
        result: List[TraceStep] = []
        for entry in trace:
            agent = entry.get("agent", entry.get("agent_name", ""))
            reasoning = entry.get("reasoning", "")
            decision = entry.get("decision", "call_agent")
            step = entry.get("step", len(result) + 1)
            is_hesitation = self._check_hesitation(reasoning)
            is_repeat = agent in seen and (step - seen[agent] > 1)
            if agent and agent not in seen:
                seen[agent] = step
            result.append(TraceStep(
                step=step, agent=agent, reasoning=reasoning,
                decision=decision, is_hesitation=is_hesitation,
                is_repeat=is_repeat,
                outcome=entry.get("outcome", "ok"),
            ))
        return result

    def _check_hesitation(self, reasoning: str) -> bool:
        score = 0.0
        for word, weight in self.HESITATION_PATTERNS:
            if word.lower() in reasoning.lower():
                score += weight
        return score >= 0.5

    @staticmethod
    def _most_repeated(steps: List[TraceStep]) -> str:
        counts: Dict[str, int] = {}
        for s in steps:
            if s.agent:
                counts[s.agent] = counts.get(s.agent, 0) + 1
        if not counts:
            return ""
        return max(counts, key=counts.get)  # type: ignore[arg-type]

    def _detect_anomalies(self, steps: List[TraceStep], stage_count: int) -> List[str]:
        warnings: List[str] = []

        # 1. 同一 Agent 被重复调用 ≥ 2 次（可能需要合并 stage）
        agent_counts: Dict[str, int] = {}
        for s in steps:
            if s.agent:
                agent_counts[s.agent] = agent_counts.get(s.agent, 0) + 1
        for agent, count in agent_counts.items():
            if count >= 3:
                warnings.append(f"🔁 {agent} 被调用 {count} 次 — 可能 task 拆分过细，建议合并为一个 stage")
            elif count >= 2:
                warnings.append(f"🔄 {agent} 被调用 {count} 次 — 检查是否应设为返回后再用")

        # 2. 步数和 stage 数差异过大
        if stage_count > 0 and len(steps) > stage_count * 1.5:
            warnings.append(f"📊 实际执行 {len(steps)} 步，预期 {stage_count} 个 stage — Agent 可能在绕弯路")

        # 3. 多步犹豫
        hesitation = [s for s in steps if s.is_hesitation]
        if len(hesitation) >= 3:
            warnings.append(f"🤔 Supervisor 在 {len(hesitation)} 步中表达了犹豫 — Spec 的阶段划分可能不够清晰")

        # 4. 推理太短（可能 Supervisor 没认真思考）
        short_reason = [s for s in steps if len(s.reasoning) < 20]
        if len(short_reason) >= len(steps) * 0.5 and len(steps) >= 3:
            warnings.append("⚡ Supervisor 推理文本过短 — 可能未充分分析就选了 Agent")

        # 5. 超时/错误步
        errors = [s for s in steps if s.outcome in ("timeout", "error")]
        if errors:
            warnings.append(f"❌ {len(errors)} 步执行失败({', '.join(s.agent for s in errors)})")

        return warnings

    def _suggest_spec_changes(
        self, steps: List[TraceStep], stage_count: int, goal: str
    ) -> List[str]:
        suggestions: List[str] = []

        # 根据重复调用 Agent → 建议调整 stage 配置
        agent_counts: Dict[str, int] = {}
        for s in steps:
            if s.agent:
                agent_counts[s.agent] = agent_counts.get(s.agent, 0) + 1
        for agent, count in agent_counts.items():
            if count >= 3:
                suggestions.append(
                    f"Stage '{agent}' 被重复调用 — 建议检查 dependency 配置，"
                    f"或将其拆分为有明确上下文的子 Agent"
                )

        # 基于犹豫 → 建议补充 Spec 中的阶段划分说明
        hesitation = [s for s in steps if s.is_hesitation]
        if hesitation:
            agents_in_hesitation = list(dict.fromkeys(s.agent for s in hesitation if s.agent))
            suggestions.append(
                f"Supervisor 在阶段 {', '.join(agents_in_hesitation[:3])} 之间存在犹豫 — "
                f"建议在 Spec 的 pipeline_stage 中明确各阶段的输出依赖关系"
            )

        # 基于步数过多 → 建议限制
        if stage_count > 0 and len(steps) > stage_count * 2:
            suggestions.append(
                f"建议在 PipelineConfig 中设置 max_steps={stage_count + 2} 防止过度执行"
            )

        return suggestions

    def format_chain(self, summary: TraceSummary) -> str:
        """生成决策链的文本展示，适合嵌入前端或诊断面板。"""
        lines = [f"## {summary.spec_id} 执行决策链 ({summary.total_steps} 步)"]
        for s in summary.steps:
            flag = ""
            if s.is_hesitation:
                flag += "🤔"
            if s.is_repeat:
                flag += "🔄"
            action = "FINISH" if s.decision == "finish" else f"→ {s.agent}"
            reasoning_short = s.reasoning[:100]
            lines.append(f"{s.step}. {flag}{action}  — {reasoning_short}")
        return "\n".join(lines)

    def format_anomalies(self, summary: TraceSummary) -> str:
        """生成异常报告的文本展示。"""
        if not summary.anomaly_warnings:
            return "✅ 未检测到异常"
        return "\n".join(summary.anomaly_warnings)

    def format_suggestions(self, summary: TraceSummary) -> str:
        """生成 Spec 调整建议的文本展示。"""
        if not summary.spec_suggestions:
            return "✅ 当前 Spec 无需调整"
        return "\n".join(f"- {s}" for s in summary.spec_suggestions)


# ── Singleton ──

_viz_instance: Optional[TraceVisualizer] = None


def get_trace_visualizer() -> TraceVisualizer:
    global _viz_instance
    if _viz_instance is None:
        _viz_instance = TraceVisualizer()
    return _viz_instance
