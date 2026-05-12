from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentMetadata
from ...apps.document_intelligence.answer_strategy import choose_answer_strategy
from ...apps.document_intelligence.question_analysis import analyze_question
from ...apps.document_intelligence.retrieval_policy import choose_retrieval_policy
from ...apps.document_intelligence.strategy_resolver import resolve_strategy as _resolve_strategy
from ...harness.interfaces import AgentConfig, AgentContext, AgentResult, AgentStatus
from ...apps.skills import get_skill_registry
from ...harness.syscalls.skill import sys_skill_call
from ...harness.kernel.runtime import get_kernel_runtime
from ...services.conversations import ConversationService
from ...apps.multimodal_kb.service import load_doc_kinds


def _build_turn_summary(question: str, answer: str) -> str:
    q = str(question or "").strip()
    a = str(answer or "").strip()
    if not a:
        return f"用户提问：{q}"
    return f"用户提问：{q}；本轮回答要点：{a[:160]}"


def _load_doc_kinds(*, tenant_id: str, doc_ids: List[str]) -> List[str]:
    return load_doc_kinds(tenant_id=tenant_id, doc_ids=doc_ids)


def _extract_answer_from_loop_output(output: Any) -> str:
    if isinstance(output, dict):
        return str(output.get("answer") or output.get("content") or output.get("output") or "")
    if isinstance(output, str):
        return output
    return ""


class MaterialsChatAgent(BaseAgent):
    def __init__(self, config: AgentConfig, **kwargs):
        super().__init__(config=config, model=None, loop_type="react", **kwargs)
        self._metadata = AgentMetadata(
            name="MaterialsChatAgent",
            description="围绕选定资料进行连续对话的受约束 Agent",
            version="1.0.1",
            capabilities=["grounded_conversation", "multi_document_query", "session_memory"],
            supported_loop_types=["react"],
        )
        self._skills: List[Any] = []

    async def execute(self, context: AgentContext) -> AgentResult:
        try:
            vars0 = dict(context.variables or {})
            scope = dict(vars0.get("scope") or {})
            options = dict(vars0.get("options") or {})
            tenant_id = str(vars0.get("tenant_id") or "default")
            session_id = str(context.session_id or "default")
            user_id = str(context.user_id or "system")
            question = ""
            if context.messages:
                question = str(context.messages[-1].get("content") or "").strip()
            if not question:
                question = str(vars0.get("message") or "").strip()
            if not question:
                return AgentResult(success=False, error="message_required")

            doc_ids = [str(x).strip() for x in (scope.get("doc_ids") or []) if str(x).strip()]
            collection_id = str(scope.get("collection_id") or "default")
            if not doc_ids:
                return AgentResult(success=False, error="conversation_scope_empty")
            doc_kinds = _load_doc_kinds(tenant_id=tenant_id, doc_ids=doc_ids)

            runtime = get_kernel_runtime()
            store = getattr(runtime, "execution_store", None) if runtime else None
            convo = ConversationService(store) if store is not None else None
            context_pack: Dict[str, Any] = {}
            if convo is not None:
                try:
                    context_pack = await convo.build_conversation_context(session_id=session_id, tenant_id=tenant_id, limit=8)
                except Exception:
                    context_pack = {}

            enhanced_question = question
            turn_summaries = list((context_pack or {}).get("turn_summaries") or [])
            analysis = analyze_question(
                question=question,
                scope=scope,
                recent_turn_summaries=turn_summaries,
                doc_kinds=doc_kinds,
            )
            intent = str(analysis.get("intent") or "fact_lookup")
            if bool(analysis.get("follow_up")) and turn_summaries:
                enhanced_question = f"{question}\n\n对话上下文：\n" + "\n".join(f"- {x}" for x in turn_summaries[-4:])
            retrieval_policy = choose_retrieval_policy(analysis=analysis, scope=scope, doc_kinds=doc_kinds)
            answer_strategy = choose_answer_strategy(analysis=analysis, retrieval_policy=retrieval_policy)
            skill_name = str(retrieval_policy.get("skill_name") or ("doc_query" if len(doc_ids) == 1 else "multi_doc_query"))
            skill_params: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "collection_id": collection_id,
                "question": enhanced_question,
                "top_k": int(retrieval_policy.get("top_k") or options.get("top_k") or 8),
                "analysis": analysis,
                "retrieval_policy": retrieval_policy,
                "answer_strategy": answer_strategy,
            }
            if len(doc_ids) == 1:
                skill_params["doc_id"] = doc_ids[0]
            else:
                skill_params["doc_ids"] = doc_ids

            registry = get_skill_registry()
            skill = registry.get(skill_name)
            if not skill:
                return AgentResult(success=False, error=f"skill_not_found:{skill_name}")

            if self._model is None and self._config.metadata.get("model"):
                try:
                    await self.initialize(self._config)
                except Exception:
                    pass

            if self._model is not None:
                self._skills = [skill]
                task_message = (
                    f"请使用技能 '{skill_name}' 检索并回答以下问题。\n"
                    f"问题：{enhanced_question}\n"
                    f"技能参数（JSON）：{json.dumps(skill_params, ensure_ascii=False)}\n"
                    f"策略意图：{intent}\n"
                    f"回答策略：{json.dumps(answer_strategy, ensure_ascii=False)}\n"
                    f"\n直接调用技能并返回结果。"
                )
                context.messages = list(context.messages or []) + [{"role": "user", "content": task_message}]
                result = await super().execute(context)
                answer = _extract_answer_from_loop_output(result.output)
                out = result.output if isinstance(result.output, dict) else {}
            else:
                response = await sys_skill_call(skill, skill_params, user_id=user_id, session_id=session_id)
                if not response.success:
                    return AgentResult(success=False, error=str(response.error or f"{skill_name}_failed"))
                out = dict(response.output or {})
                answer = str(out.get("answer") or "").strip()

            citations = list(out.get("citations") or [])
            turn_summary = _build_turn_summary(question, answer)
            mode = str(out.get("mode") or "").strip()
            strategy, skills_used = _resolve_strategy(
                doc_count=len(doc_ids),
                intent=intent,
                mode=mode,
                route=str(retrieval_policy.get("route") or ""),
                default_skill=skill_name,
            )
            run_id = str(vars0.get("_run_id") or "").strip() or None

            if convo is not None and answer:
                try:
                    await convo.append_conversation_assistant_message(
                        tenant_id=tenant_id,
                        session_id=session_id,
                        user_id=user_id,
                        content=answer,
                        citations=citations,
                        turn_summary=turn_summary,
                        strategy=strategy,
                        mode=mode,
                        intent=intent,
                        skills_used=skills_used,
                        analysis=analysis,
                        retrieval_policy=retrieval_policy,
                        answer_strategy=answer_strategy,
                        run_id=run_id,
                    )
                except Exception:
                    pass

            return AgentResult(
                success=True,
                output={
                    "answer": answer,
                    "citations": citations,
                    "items": out.get("items") or [],
                    "scope_applied": scope,
                    "strategy": strategy,
                    "skills_used": skills_used,
                    "turn_summary": turn_summary,
                    "intent": intent,
                    "mode": mode,
                    "analysis": analysis,
                    "retrieval_policy": retrieval_policy,
                    "answer_strategy": answer_strategy,
                },
                metadata={
                    "intent": intent,
                    "skill_name": skill_name,
                    "strategy": strategy,
                    "mode": mode,
                    "analysis": analysis,
                    "retrieval_policy": retrieval_policy,
                    "answer_strategy": answer_strategy,
                    "doc_count": len(doc_ids),
                },
            )
        except Exception as e:
            self._status = AgentStatus.ERROR
            return AgentResult(success=False, error=str(e), metadata={"exception": type(e).__name__})
        finally:
            if self._status != AgentStatus.ERROR:
                self._status = AgentStatus.COMPLETED


def create_materials_chat_agent(config: AgentConfig, **kwargs) -> MaterialsChatAgent:
    return MaterialsChatAgent(config=config, **kwargs)
