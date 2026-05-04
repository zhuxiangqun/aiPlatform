from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentMetadata
from ...apps.document_intelligence.answer_strategy import choose_answer_strategy
from ...apps.document_intelligence.question_analysis import analyze_question
from ...apps.document_intelligence.retrieval_policy import choose_retrieval_policy
from ...apps.multimodal_kb.db import KBSqlite
from ...apps.multimodal_kb.storage import get_tenant_storage
from ...harness.interfaces import AgentConfig, AgentContext, AgentResult, AgentStatus, SkillContext
from ...apps.skills import get_skill_registry
from ...harness.kernel.runtime import get_kernel_runtime
from ...services.conversations import ConversationService


def _build_turn_summary(question: str, answer: str) -> str:
    q = str(question or "").strip()
    a = str(answer or "").strip()
    if not a:
        return f"用户提问：{q}"
    return f"用户提问：{q}；本轮回答要点：{a[:160]}"


def _load_doc_kinds(*, tenant_id: str, doc_ids: List[str]) -> List[str]:
    if not doc_ids:
        return []
    try:
        st = get_tenant_storage(tenant_id)
        db = KBSqlite(st.db_path)
        db.ensure_schema()
        with db.connect() as conn:
            placeholders = ",".join(["?"] * len(doc_ids))
            rows = conn.execute(
                f"SELECT doc_id, kind FROM documents WHERE tenant_id=? AND doc_id IN ({placeholders})",
                (tenant_id, *doc_ids),
            ).fetchall()
        return [str(dict(r).get("kind") or "").strip().lower() for r in rows if str(dict(r).get("kind") or "").strip()]
    except Exception:
        return []


def _resolve_strategy(
    *,
    doc_count: int,
    intent: str,
    mode: str,
    route: str,
    default_skill: str,
) -> tuple[str, List[str]]:
    mode0 = str(mode or "").strip().lower()
    route0 = str(route or "").strip().lower()
    if route0 == "video_fact_lookup":
        return "video_fact_lookup", ["video_fact_lookup"]
    if route0 == "video_window_query":
        if intent == "summary":
            return "video_summary", ["video_window_query"]
        return "video_window_query", ["video_window_query"]
    if route0 == "multi_doc_query":
        if intent == "compare":
            return "multi_doc_compare", ["multi_doc_query"]
        if intent == "summary":
            return "multi_doc_summary", ["multi_doc_query"]
        return "multi_doc_query", ["multi_doc_query"]
    if route0 == "single_doc_query":
        if intent == "summary":
            return "single_doc_summary", [default_skill]
        if intent == "evidence_trace":
            return "single_doc_evidence_trace", [default_skill]
        return "single_doc_query", [default_skill]
    if mode0.startswith("video_window"):
        if intent == "summary":
            return "video_summary", ["video_window_query"]
        return "video_window_query", ["video_window_query"]
    if doc_count > 1:
        if intent == "compare":
            return "multi_doc_compare", ["multi_doc_query"]
        if intent == "summary":
            return "multi_doc_summary", ["multi_doc_query"]
        return "multi_doc_query", ["multi_doc_query"]
    if intent == "summary":
        return "single_doc_summary", [default_skill]
    if intent == "evidence_trace":
        return "single_doc_evidence_trace", [default_skill]
    return "single_doc_query", [default_skill]


class MaterialsChatAgent(BaseAgent):
    def __init__(self, config: AgentConfig, **kwargs):
        super().__init__(config=config, model=None, loop_type="react", **kwargs)
        self._metadata = AgentMetadata(
            name="MaterialsChatAgent",
            description="围绕选定资料进行连续对话的受约束 Agent",
            version="1.0.0",
            capabilities=["grounded_conversation", "multi_document_query", "session_memory"],
            supported_loop_types=[],
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        self._status = AgentStatus.RUNNING
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
            sctx = SkillContext(session_id=session_id, user_id=user_id, variables={"tenant_id": tenant_id}, metadata={"tenant_id": tenant_id})
            sres = await skill.execute(sctx, skill_params)
            if not sres.success:
                return AgentResult(success=False, error=str(sres.error or f"{skill_name}_failed"))
            out = dict(sres.output or {})
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
