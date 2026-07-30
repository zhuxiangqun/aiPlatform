"""
DecisionCapture — 决策捕获注入层 (Phase 41)

在 ReAct 循环的关键决策点自动记录 agent 的选择:
  - sys_tool_call 前: 记录"为什么选这个工具"
  - sys_skill_call 前: 记录"为什么选这个技能"
  - 降级触发: 记录 fallback 原因
  - 参数选择: 记录参数覆盖原因

注入点: sys_tool_call (tool.py) 和 sys_skill_call (skill.py) 的 trace_context

调用者:
  - sys_tool_call → capture_tool_decision()
  - sys_skill_call → capture_skill_decision()
  - PipelineEngine._exec_stage → capture_fallback_decision()

不依赖 Agent 层面的 ReAct 循环修改 — 所有决策信息从 trace_context 提取。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Decision Types ────────────────────────────────────────────────────────

TOOL_SELECTION = "tool_selection"
SKILL_SELECTION = "skill_selection"
FALLBACK_TRIGGER = "fallback_trigger"
PARAMETER_CHOICE = "parameter_choice"
ACTION_SELECTION = "action_selection"
APPROVAL_OVERRIDE = "approval_override"


# ── Trace Context Extraction ──────────────────────────────────────────────

def _extract_context_versions(trace_context: Optional[Dict]) -> Dict[str, str]:
    """从 trace_context 中提取上下文版本信息."""
    if not trace_context:
        return {}
    return {
        "ontology_version": trace_context.get("ontology_version", ""),
        "kb_collection_version": trace_context.get("kb_collection_version", ""),
        "context_snapshot_id": trace_context.get("context_snapshot_id", ""),
        "policy_version": trace_context.get("policy_version", ""),
        "constraint_checks": trace_context.get("constraint_checks", ""),
    }


def _extract_actor_info(trace_context: Optional[Dict]) -> Dict[str, str]:
    """从 trace_context 中提取 actor 信息."""
    if not trace_context:
        return {"agent_id": "", "actor_role": ""}
    return {
        "agent_id": trace_context.get("agent_id", ""),
        "actor_role": trace_context.get("role", "") or trace_context.get("actor_role", ""),
        "run_id": trace_context.get("run_id", ""),
        "trace_id": trace_context.get("trace_id", ""),
    }


# ── Decision Capture API ──────────────────────────────────────────────────

async def capture_tool_decision(
    tool_name: str,
    tool_args: Optional[Dict[str, Any]],
    trace_context: Optional[Dict[str, Any]],
    *,
    reason: str = "",
    alternatives: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """在 sys_tool_call 执行前捕获工具选择决策.

    Args:
        tool_name: 被调用的工具名
        tool_args: 工具参数
        trace_context: agent 的 trace 上下文
        reason: 选择此工具的原因 (从 agent 推理中提取)
        alternatives: 候选工具列表 [{tool, score, reason}]

    Returns:
        decision_id 或 None (如果决策捕获失败)
    """
    try:
        from core.harness.infrastructure.lineage_store import LineageStore, DecisionRecord

        actor = _extract_actor_info(trace_context)
        versions = _extract_context_versions(trace_context)

        record = DecisionRecord(
            run_id=actor.get("run_id", ""),
            trace_id=actor.get("trace_id", ""),
            agent_id=actor.get("agent_id", ""),
            actor_role=actor.get("actor_role", ""),
            decision_type=TOOL_SELECTION,
            chosen_option=tool_name,
            choice_reasoning=reason,
            options_considered=alternatives or _build_tool_alternatives(tool_name, trace_context),
            context_snapshot_id=versions.get("context_snapshot_id", ""),
            ontology_version=versions.get("ontology_version", ""),
            kb_collection_version=versions.get("kb_collection_version", ""),
            policy_version=versions.get("policy_version", ""),
            constraint_checks=str(versions.get("constraint_checks", "")),
            source_call="sys_tool_call",
        )

        store = LineageStore.get()
        return store.insert(record)

    except Exception as e:
        logger.debug("Tool decision capture skipped: %s", e)
        return None


async def capture_skill_decision(
    skill_name: str,
    params: Dict[str, Any],
    trace_context: Optional[Dict[str, Any]],
    *,
    reason: str = "",
    alternatives: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """在 sys_skill_call 执行前捕获技能选择决策."""
    try:
        from core.harness.infrastructure.lineage_store import LineageStore, DecisionRecord

        actor = _extract_actor_info(trace_context)
        versions = _extract_context_versions(trace_context)

        record = DecisionRecord(
            run_id=actor.get("run_id", ""),
            trace_id=actor.get("trace_id", ""),
            agent_id=actor.get("agent_id", ""),
            actor_role=actor.get("actor_role", ""),
            decision_type=SKILL_SELECTION,
            chosen_option=skill_name,
            choice_reasoning=reason,
            options_considered=alternatives,
            context_snapshot_id=versions.get("context_snapshot_id", ""),
            ontology_version=versions.get("ontology_version", ""),
            kb_collection_version=versions.get("kb_collection_version", ""),
            policy_version=versions.get("policy_version", ""),
            source_call="sys_skill_call",
        )

        store = LineageStore.get()
        return store.insert(record)

    except Exception as e:
        logger.debug("Skill decision capture skipped: %s", e)
        return None


async def capture_fallback_decision(
    stage_name: str,
    from_model: str,
    to_model: str,
    reason: str,
    trace_context: Optional[Dict[str, Any]],
) -> Optional[str]:
    """在 Pipeline 降级时捕获降级决策."""
    try:
        from core.harness.infrastructure.lineage_store import LineageStore, DecisionRecord

        actor = _extract_actor_info(trace_context)
        versions = _extract_context_versions(trace_context)

        record = DecisionRecord(
            run_id=actor.get("run_id", ""),
            trace_id=actor.get("trace_id", ""),
            agent_id=actor.get("agent_id", ""),
            actor_role=actor.get("actor_role", ""),
            decision_type=FALLBACK_TRIGGER,
            chosen_option=to_model,
            choice_reasoning=f"Stage {stage_name}: 从 {from_model} 降级到 {to_model}. 原因: {reason}",
            options_considered=[
                {"tool": from_model, "score": 0, "reason": f"不可用: {reason}"},
                {"tool": to_model, "score": 1, "reason": "降级选择"},
            ],
            context_snapshot_id=versions.get("context_snapshot_id", ""),
            ontology_version=versions.get("ontology_version", ""),
            kb_collection_version=versions.get("kb_collection_version", ""),
            outcome_status="logged",
            source_call="pipeline_engine",
        )

        store = LineageStore.get()
        return store.insert(record)

    except Exception as e:
        logger.debug("Fallback decision capture skipped: %s", e)
        return None


async def update_decision_outcome(
    decision_id: str,
    outcome_status: str,
    outcome_summary: str = "",
) -> None:
    """更新之前记录的决策结果."""
    if not decision_id:
        return
    try:
        from core.harness.infrastructure.lineage_store import LineageStore

        store = LineageStore.get()
        store.update_outcome(decision_id, outcome_status, outcome_summary)
    except Exception as e:
        logger.debug("Decision outcome update skipped: %s", e)


# ── Helpers ────────────────────────────────────────────────────────────────

def _build_tool_alternatives(
    chosen_tool: str,
    trace_context: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """从 trace_context 中构建候选工具列表."""
    available_tools = (trace_context or {}).get("available_tools", [])
    if not available_tools:
        return []

    alternatives = []
    for tool_info in available_tools:
        name = tool_info if isinstance(tool_info, str) else tool_info.get("name", "")
        if name and name != chosen_tool:
            alternatives.append({
                "tool": name,
                "score": 0,
                "reason": "available but not chosen",
            })

    # Mark the chosen one
    alternatives.insert(0, {
        "tool": chosen_tool,
        "score": 1,
        "reason": "selected",
    })

    return alternatives


def inject_context_version_pin(
    trace_context: Dict[str, Any],
    *,
    ontology_version: str = "",
    kb_collection_version: str = "",
    context_snapshot_id: str = "",
) -> None:
    """在 MemoryManager.build_context() 后注入上下文版本到 trace_context.

    这样后续的 sys_tool_call / sys_skill_call 可以通过 _extract_context_versions()
    自动读取并记录到 lineage_decisions 表中.
    """
    if ontology_version:
        trace_context["ontology_version"] = ontology_version
    if kb_collection_version:
        trace_context["kb_collection_version"] = kb_collection_version
    if context_snapshot_id:
        trace_context["context_snapshot_id"] = context_snapshot_id
