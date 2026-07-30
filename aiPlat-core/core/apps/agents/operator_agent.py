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
import os
import time
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentMetadata
from core.harness.interfaces import AgentConfig, AgentContext, AgentResult

logger = logging.getLogger("aiplat.operator_agent")


class OperatorAgent(BaseAgent):  # noqa: agent-subclass-approved — §55: genuine new type (operational decision-support)
    """Operational decision-support agent.

    Usage:
        agent = OperatorAgent(config)
        result = await agent.execute(context)  # noqa: agent-comms-ok — this is a docstring example, not real code
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

    async def _execute_impl(self, context: AgentContext) -> AgentResult:  # noqa: agent-init-legacy — single-shot decision, no conversational context to compress
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

            op_messages = [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": f"当前问题：{question}\n\n请基于以上运行时上下文和决策框架，输出结构化JSON决策。"},
            ]
            resp = await sys_llm_generate(
                None,
                op_messages,
                model_name=best_model_for_purpose("doc_llm", messages=op_messages),
                temperature=0.3,
                max_tokens=2000,
            )
            answer = getattr(resp, "content", "") or str(resp)
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
            return AgentResult(success=False, error=str(e))

        # ── Parse structured decision ──
        decision = self._parse_decision(answer)

        # Phase 15: Lightweight retry on low-confidence outputs
        _retried = False
        try:
            if decision.get("confidence", 1.0) < 0.5:
                logger.info("Low confidence (%.2f), retrying with temperature=0.2", decision.get("confidence", 0))
                retry_resp = await sys_llm_generate(
                    None,
                    op_messages,
                    model_name=best_model_for_purpose("doc_llm", messages=op_messages),
                    temperature=0.2,
                    max_tokens=2000,
                )
                retry_answer = getattr(retry_resp, "content", "") or str(retry_resp)
                retry_decision = self._parse_decision(retry_answer)
                if retry_decision.get("confidence", 0) > decision.get("confidence", 0):
                    decision = retry_decision
                    _retried = True
        except Exception as e:
            logger.debug("Retry skipped: %s", e)

        # Phase 22: Human confirmation for critical decisions
        _confirmation_level = os.getenv("AIPLAT_OPERATOR_CONFIRMATION_LEVEL", "critical")
        _paused_for_confirmation = False
        _approval_id = None
        _exec_id = ""

        if _confirmation_level != "none":
            should_pause = (_confirmation_level == "all")
            if not should_pause and _confirmation_level == "critical":
                should_pause = (
                    decision.get("severity", "") == "critical"
                    or decision.get("can_continue") == False
                    or decision.get("confidence", 1.0) < 0.5
                )
            if should_pause:
                _exec_id = str(vars0.get("_run_id") or "") or f"op-{int(time.time())}-{session_id[:8]}"
                try:
                    from core.harness.infrastructure.gates.policy_gate import PolicyGate
                    gate = PolicyGate()
                    pr = await gate.check_agent(
                        user_id=user_id,
                        agent_id="operator_agent",
                        agent_args={
                            "_tenant_id": vars0.get("tenant_id", "default"),
                            "_approval_required": True,
                        },
                    )
                    _approval_id = pr.approval_request_id if hasattr(pr, "approval_request_id") else None
                except Exception:
                    _approval_id = None

                # Cache execution state for resume
                try:
                    from datetime import datetime, timezone
                    from core.api.routers.agents import _paused_agent_executions
                    _paused_agent_executions[_exec_id] = {
                        "agent_id": "operator_agent",
                        "request": dict(vars0),
                        "user_id": user_id,
                        "session_id": session_id,
                        "approval_request_id": _approval_id,
                        "_decision_snapshot": decision,
                        "_original_question": question,
                        "_paused_phase": "operator_confirmation",
                        "ttl_seconds": int(os.getenv("AIPLAT_OPERATOR_APPROVAL_TIMEOUT", "3600")),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    _paused_for_confirmation = True
                except Exception:
                    _paused_for_confirmation = False

        if _paused_for_confirmation:
            return AgentResult(
                success=False,
                error="approval_required",
                output=answer,
                metadata={
                    "phase": "operator_decision",
                    "decision": decision,
                    "elapsed_ms": int((time.time() - _t0) * 1000),
                    "approval_required": True,
                    "approval_reason": (
                        f"Severity={decision.get('severity')}, "
                        f"can_continue={decision.get('can_continue')}, "
                        f"confidence={decision.get('confidence')}"
                    ),
                    "approval_request_id": _approval_id,
                    "execution_id": _exec_id,
                    "resume_endpoint": f"/api/core/agents/executions/{_exec_id}/resume",
                    "retried": _retried,
                },
            )

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
                "retried": _retried,
            },
        )

    # ── Decision parsing ──────────────────────────────────────

    def _parse_decision(self, text: str) -> Dict[str, Any]:
        """Extract structured JSON from LLM output."""
        # Try direct JSON parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass  # noqa: cleanup-best-effort
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
    """Minimal fallback when prompt_loader is unavailable.
    Primary prompt is registered as 'operator-decision' in prompt_loader.py."""
    return "Output a JSON decision with fields: severity, impact, recommended_actions, can_continue, confidence."


def create_operator_agent(config: AgentConfig, **kwargs) -> OperatorAgent:
    return OperatorAgent(config=config, **kwargs)

