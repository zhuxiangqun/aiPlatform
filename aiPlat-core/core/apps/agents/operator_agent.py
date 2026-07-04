"""
OperatorAgent (Phase 10.4) — Decision-support AI for operational scenarios.

Unlike MaterialsChatAgent ("what is it?"), OperatorAgent answers
"what should we do now?" by consuming:

  1. RunContext (Phase 10.1-10.3) — runtime operational state
  2. Ontology (GraphIndex) — static entity knowledge
  3. Decision prompt (operator-decision) — structured output guidance

Output is a structured JSON decision with severity, impact assessment,
recommended actions, and notification targets. Can be mapped to Action
Types for automated workflow triggering.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentMetadata
from core.harness.interfaces import AgentConfig, AgentContext, AgentResult

logger = logging.getLogger("aiplat.operator_agent")


class OperatorAgent(BaseAgent):
    """Operational decision-support agent.

    Usage:
        agent = OperatorAgent(config)
        result = await agent.execute(context)
        # result.metadata["decision"] → structured JSON
    """

    def __init__(self, config: AgentConfig, **kwargs):
        cfg = dict(config.__dict__) if hasattr(config, '__dict__') else {}
        cfg.setdefault("name", "operator_agent")
        cfg.setdefault("agent_type", "operator")
        super().__init__(config=config, **kwargs)
        self._metadata = AgentMetadata(
            name="operator_agent",
            description="Operational decision-support — evaluates runtime context and recommends actions",
            version="10.4.0",
            capabilities=["decision_support", "impact_assessment", "action_recommendation"],
            supported_loop_types=["react"],
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        try:
            return await self._execute_impl(context)
        except Exception as e:
            logger.warning("OperatorAgent failed: %s", e, exc_info=True)
            return AgentResult(
                success=False,
                error=str(e),
                metadata={"phase": "operator_decision", "source": "exception"},
            )

    async def _execute_impl(self, context: AgentContext) -> AgentResult:
        _t0 = time.time()
        vars0 = dict(context.variables or {})
        run_context = vars0.get("_run_context")
        session_id = str(context.session_id or "default")

        question = ""
        if context.messages:
            question = str(context.messages[-1].get("content") or "").strip()
        if not question:
            question = str(vars0.get("message") or "").strip()
        if not question:
            return AgentResult(success=False, error="message_required")

        # ── Build decision context ──
        rc_text = ""
        if run_context:
            try:
                from core.harness.kernel.types import RunContext

                if isinstance(run_context, dict):
                    rc_obj = RunContext(**run_context)
                elif isinstance(run_context, RunContext):
                    rc_obj = run_context
                else:
                    rc_obj = None
                if rc_obj:
                    rc_text = rc_obj.to_compact()
            except Exception:
                if isinstance(run_context, dict):
                    parts = [f"{k}: {v}" for k, v in run_context.items() if v]
                    rc_text = " | ".join(parts)

        # ── Load operator decision prompt ──
        try:
            from core.harness.utils.prompt_loader import _sync_resolve
            decision_prompt = _sync_resolve("operator-decision")
        except Exception:
            decision_prompt = _default_decision_prompt()

        # ── Assemble system prompt ──
        sys_content = decision_prompt
        if rc_text:
            sys_content += f"\n\n[运行时上下文]\n{rc_text}"

        # ── Call LLM for structured decision ──
        try:
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.model_injection import best_model_for_purpose

            resp = await sys_llm_generate(
                None,
                [
                    {"role": "system", "content": sys_content},
                    {"role": "user", "content": f"当前问题：{question}\n\n请基于以上运行时上下文和决策框架，输出结构化JSON决策。"},
                ],
                model_name=best_model_for_purpose("doc_llm"),
                temperature=0.3,
                max_tokens=2000,
            )
            answer = getattr(resp, "content", "") or str(resp)
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
            return AgentResult(success=False, error=str(e))

        # ── Parse structured decision ──
        decision = self._parse_decision(answer)

        # ── Action bridge: fire webhooks for recommended actions ──
        action_results = []
        try:
            if decision.get("recommended_actions"):
                from core.harness.actions.action_bridge import execute_decision_actions
                ctx = {
                    "entity_id": vars0.get("entity", ""),
                    "domain_id": vars0.get("domain_id", "default"),
                    "timestamp": str(int(time.time())),
                }
                action_results = await execute_decision_actions(decision, context=ctx)
        except Exception as e:
            logger.debug("Action bridge skipped: %s", e)

        elapsed_ms = int((time.time() - _t0) * 1000)
        return AgentResult(
            success=bool(decision),
            output=answer,
            metadata={
                "phase": "operator_decision",
                "decision": decision,
                "elapsed_ms": elapsed_ms,
                "session_id": session_id,
                "has_run_context": bool(run_context),
                "actions_fired": len(action_results),
                "action_results": action_results,
            },
        )

    # ── Decision parsing ──────────────────────────────────────

    def _parse_decision(self, text: str) -> Dict[str, Any]:
        """Extract structured JSON from LLM output."""
        # Try direct JSON parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
        # Try extracting ───...─── delimited JSON
        import re
        for pattern in [
            r"```(?:json)?\s*\n(.*?)\n```",
            r"```(?:json)?\s*(\{.*?\})\s*```",
            r"\{[\s\S]*\"severity\"[\s\S]*\}",
        ]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1) if m.lastindex else m.group(0))
                except (json.JSONDecodeError, TypeError, IndexError):
                    continue
        return {"raw_output": text[:500], "parse_status": "fallback"}


def _default_decision_prompt() -> str:
    """Fallback decision prompt when prompt_loader is not available."""
    return """你是一个企业运维决策助手。根据运行时上下文和问题，输出结构化JSON决策。

输出格式要求严格为JSON:
```json
{
  "severity": "critical|elevated|normal",
  "severity_reason": "严重程度判断依据",
  "impact": {
    "affected_entities": ["受影响实体列表"],
    "estimated_downtime": "预计停机时长",
    "business_risk": "业务风险描述"
  },
  "can_continue": true|false,
  "recommended_actions": [
    {"action": "具体行动", "urgency": "immediate|within_1h|within_24h", "target": "责任方"}
  ],
  "decision_rationale": "决策理由",
  "confidence": 0.0-1.0
}
```

决策原则:
1. 先评估严重程度 — 运行时上下文的 priority 字段是权威来源
2. 再评估影响范围 — 关联实体和业务上下文决定紧迫度
3. 最后给出可执行建议 — 每个建议必须指定执行方和时限"""


def create_operator_agent(config: AgentConfig, **kwargs) -> OperatorAgent:
    return OperatorAgent(config=config, **kwargs)
