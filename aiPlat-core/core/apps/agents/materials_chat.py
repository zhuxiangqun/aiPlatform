from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from core.harness.utils.model_injection import best_model_for_purpose
from core.harness.utils.prompt_loader import _sync_resolve as _resolve

from .base import BaseAgent, AgentMetadata
from core.apps.document_intelligence.answer_strategy import choose_answer_strategy
from core.apps.document_intelligence.question_analysis import analyze_question
from core.apps.document_intelligence.retrieval_policy import choose_retrieval_policy
from core.apps.document_intelligence.strategy_resolver import resolve_strategy as _resolve_strategy
from core.harness.interfaces import AgentConfig, AgentContext, AgentResult, AgentStatus
from core.apps.skills import get_skill_registry
from core.harness.syscalls.skill import sys_skill_call
from core.harness.kernel.runtime import get_kernel_runtime
from core.services.conversations import ConversationService
from core.apps.document_intelligence.kb_provider import get_kb_load_doc_kinds_fn
import logging

from core.harness.knowledge.query_guard import sanitize_query
from core.harness.context.run_context import inject_run_context
from core.harness.ontology_engine.run_context_builder import (
    build_run_context_from_graph,
    merge_run_context,
)
from core.harness.data_source.realtime_context import fetch_realtime_context
from core.harness.evaluation.self_review import self_review
from core.harness.evaluation.rag_diagnosis import diagnose_rag_quality


def _enforce_scope(collection_id: str, domain_id: str) -> bool:
    """§5.62: Verify scope is set — delegates to shared query_guard."""
    from core.harness.knowledge.query_guard import enforce_scope
    return enforce_scope(collection_id, domain_id)


def _build_turn_summary(question: str, answer: str) -> str:
    """Delegate to shared turn_summarizer."""
    from core.harness.utils.turn_summarizer import build_turn_summary
    return build_turn_summary(question, answer)


def _load_doc_kinds(*, tenant_id: str, doc_ids: List[str]) -> List[str]:
    return get_kb_load_doc_kinds_fn()(tenant_id=tenant_id, doc_ids=doc_ids)


def _assemble_chat_system_msgs(
    domain_config: Dict[str, Any],
    run_context: Optional[dict],
) -> List[Dict[str, str]]:
    """Assemble system prompt messages for chat answer generation.

    Eliminates the 3x duplicated pattern: domain prompt → run_context → base role.
    """
    msgs: List[Dict[str, str]] = []
    prompt_id = domain_config.get("system_prompt_id")
    if prompt_id:
        msgs.append({"role": "system", "content": _resolve(prompt_id)})
    inject_run_context(msgs, run_context)
    msgs.append({"role": "system", "content": _resolve("kb-chat-system-role")})
    return msgs


def _extract_answer_from_loop_output(output: Any) -> str:
    """Delegate to shared answer_extractor."""
    from core.harness.utils.answer_extractor import extract_answer_from_output
    return extract_answer_from_output(output)


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
        import asyncio
        try:
            return await asyncio.wait_for(self._execute_impl(context), timeout=120)
        except TimeoutError:
            return AgentResult(success=False, error="timeout", metadata={"reason": "execution exceeded 120s"})

    async def _execute_impl(self, context: AgentContext) -> AgentResult:
        try:
            from core.harness.utils.pipeline_tracer import PipelineTracer
            tracer = PipelineTracer()
            _trace = tracer
            pipeline_trace = tracer._entries  # direct reference for AgentResult output

            vars0 = dict(context.variables or {})
            run_context = vars0.get("_run_context")  # Phase 10.1: runtime context from API caller
            run_id = str(vars0.get("_run_id") or "").strip() or None
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

            # §5.63: Query sanitization
            question = sanitize_query(question)
            
            # Phase C6: Cost-aware routing — shared core capability
            from core.harness.knowledge.cost_estimator import estimate_query_cost, resolve_routing_mode
            _cost = estimate_query_cost(question, scope, options)
            _trace("成本预估", f"RAG={_cost.rag_est_tokens} vs 全量={_cost.full_est_tokens}, 选择={_cost.recommendation}",
                   rag_tokens=_cost.rag_est_tokens, full_tokens=_cost.full_est_tokens,
                   recommendation=_cost.recommendation, complexity=_cost.query_complexity)
            
            _routing_mode = resolve_routing_mode(_cost)
            _trace("路由决策", f"模式={_routing_mode}, 原因={_cost.recommendation}",
                   routing_mode=_routing_mode, cache_available=_cost.cache_saving > 0)

            # Phase 0.3: Semantic cache check — skip heavy retrieval if answer cached
            if os.getenv("AIPLAT_SEMANTIC_CACHE_ENABLED", "true").lower() in ("true", "1", "yes"):
                try:
                    from core.harness.knowledge.semantic_cache_hook import try_cache_hit
                    collection_id_pre = str(scope.get("collection_id") or vars0.get("collection_id") or "default")
                    cached = await try_cache_hit(question, collection_id_pre)
                    if cached:
                        _trace("缓存命中", f"语义缓存L1/L2", cached=True)
                        return AgentResult(
                            success=True,
                            output=cached["answer"],
                            metadata={"source": "semantic_cache", "pipeline_trace": pipeline_trace},
                        )
                except Exception:
                    import logging; logging.getLogger(__name__).debug("Semantic cache check skipped", exc_info=True)
            collection_id = str(scope.get("collection_id") or vars0.get("collection_id") or "default")
            if not _enforce_scope(collection_id, str(vars0.get("tenant_id") or "default")):
                return AgentResult(success=False, error="scope_required")
            _trace("问题理解", f"DMQR 多查询改写", query_len=len(question))
            doc_ids = [str(x).strip() for x in (scope.get("doc_ids") or []) if str(x).strip()]
            if not doc_ids and collection_id == "default":
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

            # ── Trivial query bypass: skip full RAG pipeline for sub-ms responses ──
            import re as _t_re
            _t_check = question.strip().lower()
            if any(p in _t_check for p in ("几点", "几点了", "现在时间", "今天日期", "星期几")):
                from datetime import datetime as _dt
                now = _dt.now()
                weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
                return AgentResult(success=True,
                    output={"answer": f"现在是 {now.year}年{now.month}月{now.day}日 {now.hour:02d}:{now.minute:02d}:{now.second:02d}，{weekdays[now.weekday()]}",
                            "citations": [], "items": [], "scope_applied": scope,
                            "strategy": "trivial_bypass", "skills_used": [],
                            "turn_summary": "time query", "intent": "trivial",
                            "reasoning_path": [], "pipeline_trace": pipeline_trace,
                            "quality": "trivial"},
                    metadata={"intent": "trivial", "strategy": "trivial_bypass"})
            if _t_check in ("你好", "hello", "hi", "hey", "在吗", "在不在"):
                return AgentResult(success=True,
                    output={"answer": "你好！我是知识库助手，有什么可以帮助你的？",
                            "citations": [], "items": [], "scope_applied": scope,
                            "strategy": "trivial_bypass", "skills_used": [],
                            "turn_summary": "greeting", "intent": "trivial",
                            "reasoning_path": [], "pipeline_trace": pipeline_trace,
                            "quality": "trivial"},
                    metadata={"intent": "trivial", "strategy": "trivial_bypass"})
            if _t_check in ("谢谢", "多谢", "thank", "thanks", "thank you"):
                return AgentResult(success=True,
                    output={"answer": "不客气！如果还有其他问题，随时可以问我。",
                            "citations": [], "items": [], "scope_applied": scope,
                            "strategy": "trivial_bypass", "skills_used": [],
                            "turn_summary": "thanks", "intent": "trivial",
                            "reasoning_path": [], "pipeline_trace": pipeline_trace,
                            "quality": "trivial"},
                    metadata={"intent": "trivial", "strategy": "trivial_bypass"})
            if _t_re.match(r'^[+\-]?\d+(\.\d+)?\s*[\+\-\*\/\^]\s*[+\-]?\d+(\.\d+)?$', question.strip()):
                try:
                    _result = eval(question.strip().replace("^", "**"))
                    return AgentResult(success=True,
                        output={"answer": f"{question.strip()} = {_result}",
                                "citations": [], "items": [], "scope_applied": scope,
                                "strategy": "trivial_bypass", "skills_used": [],
                                "turn_summary": "math", "intent": "trivial",
                                "reasoning_path": [], "pipeline_trace": pipeline_trace,
                                "quality": "trivial"},
                        metadata={"intent": "trivial", "strategy": "trivial_bypass"})
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

            # Lightweight complexity classifier (zero LLM, rule-based)
            # Categorize before analyze_question so ModelManager can use it for routing
            complexity = "fact_lookup"
            q_lower = question.lower()
            if any(kw in q_lower for kw in ["对比", "区别", "总结", "分析", "综合", "比较", "归纳"]):
                complexity = "multi_doc_synthesis"
            elif any(kw in q_lower for kw in ["代码", "实现", "怎么写", "如何做", "示例", "example", "code"]):
                complexity = "code_generation"
            elif any(kw in q_lower for kw in ["评估", "评分", "打分", "评测", "review"]):
                complexity = "evaluation"
            vars0["_query_complexity"] = complexity

            analysis = await analyze_question(
                question=question,
                scope=scope,
                recent_turn_summaries=turn_summaries,
                doc_kinds=doc_kinds,
            )
            intent = str(analysis.get("intent") or "fact_lookup")
            if bool(analysis.get("follow_up")) and turn_summaries:
                enhanced_question = f"{question}\n\n对话上下文：\n" + "\n".join(f"- {x}" for x in turn_summaries[-4:])
            # DMQR-RAG: Multi-query rewrite enrichment
            try:
                from core.harness.knowledge.ontology_query_mapper import rewrite_multi_dmqr
                dmqr_variants = rewrite_multi_dmqr(question, strategies=["generic", "keywords", "core"])
                if len(dmqr_variants) > 1:
                    enhanced_question = f"{enhanced_question} [variants: {' | '.join(dmqr_variants[1:4])}]"
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            retrieval_policy = choose_retrieval_policy(analysis=analysis, scope=scope, doc_kinds=doc_kinds)
            answer_strategy = choose_answer_strategy(analysis=analysis, retrieval_policy=retrieval_policy)

            # ── Domain routing (multi-domain support) ──
            from core.harness.knowledge.domain_router import DomainRouter
            router = DomainRouter()
            domain_id = router.classify(enhanced_question)
            domain_config = router.domain_config(domain_id)
            _trace("域路由", f"→ {domain_id}", domain_id=domain_id)

            # Phase 10.2: auto-populate run_context from GraphIndex entity traversal
            if domain_id:
                graph_ctx = build_run_context_from_graph(enhanced_question, domain_id)
                # Phase 10.3: fetch real-time DataSource data for dynamic fields
                entity_name = ""
                if run_context and run_context.get("entity"):
                    entity_name = str(run_context.get("entity"))
                elif graph_ctx and graph_ctx.get("entity"):
                    entity_name = str(graph_ctx.get("entity"))
                if entity_name:
                    realtime_ctx = fetch_realtime_context(entity_name, domain_id)
                else:
                    realtime_ctx = None

                # Merge chain: caller > realtime > graph
                if realtime_ctx and graph_ctx:
                    graph_ctx = merge_run_context(realtime_ctx, graph_ctx)
                if run_context and graph_ctx:
                    run_context = merge_run_context(run_context, graph_ctx)
                    _trace("运行时上下文", f"合并调用方+实时数据+Graph: entity={run_context.get('entity')}",
                           source="merged", has_realtime=bool(realtime_ctx))
                elif realtime_ctx and not graph_ctx:
                    run_context = merge_run_context(run_context, realtime_ctx) if run_context else realtime_ctx
                    _trace("运行时上下文", f"实时数据: entity={realtime_ctx.get('entity')}",
                           source="realtime_datasource")
                elif graph_ctx:
                    run_context = graph_ctx
                    _trace("运行时上下文", f"GraphIndex自动构建: entity={graph_ctx.get('entity')}",
                           source="graph_index")

            skill_name = str(retrieval_policy.get("skill_name") or ("doc_query" if len(doc_ids) == 1 else "multi_doc_query"))
            skill_params: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "collection_id": collection_id,
                "domain_id": domain_id,
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

            # ── Ontology-aware retrieval: detect target class from question ──
            ontology_class_uri: str = ""
            ontology_mapping: Dict[str, Any] = {}
            ontology_mapping_mode = domain_config.get("ontology_mapping", "best_effort")
            if ontology_mapping_mode == "mandatory":
                # Mandatory ontology mapping (config-driven), failure propagates
                from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology
                onto_mapping = map_query_to_ontology(enhanced_question, domain_id=domain_id, collection_id=collection_id)
                if onto_mapping:
                    ontology_mapping = onto_mapping
                    matched = onto_mapping.get("matched_classes") or []
                    if matched and matched[0].get("score", 0) >= 0.8:
                        ontology_class_uri = matched[0].get("uri", "")
                else:
                    logging.debug(f"ontology_query_mapper returned empty for domain={domain_id}, question={enhanced_question[:80]}")
            else:
                # Non-target domain: backward-compatible try/except
                try:
                    from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology
                    onto_mapping = map_query_to_ontology(enhanced_question, domain_id=domain_id, collection_id=collection_id)
                    if onto_mapping:
                        ontology_mapping = onto_mapping
                        matched = onto_mapping.get("matched_classes") or []
                        if matched and matched[0].get("score", 0) >= 0.8:
                            ontology_class_uri = matched[0].get("uri", "")
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
            _trace("本体感知", f"匹配类: {', '.join((m.get('label','') for m in (ontology_mapping.get('matched_classes',[]) if ontology_mapping else [])[:3])) or '无'}",
                   matched_count=len(ontology_mapping.get("matched_classes", [])) if ontology_mapping else 0)

            # ── Build reasoning path ──
            from core.harness.knowledge.orchestrated_retrieval import build_reasoning_path

            reasoning_path = build_reasoning_path(question, ontology_mapping, None)
            if ontology_class_uri and ontology_mapping:
                # Try graph traversal to extend path (shared pipeline)
                try:
                    from core.harness.knowledge.orchestrated_retrieval import traverse_ontology_graph

                    trav = traverse_ontology_graph(enhanced_question, domain_id=domain_id, max_hops=2)
                    if trav["success"]:
                        # Build reasoning path from traversal steps
                        for tpath in trav["traversal_paths"][:5]:
                            for s in tpath.steps[1:]:
                                reasoning_path.append({
                                    "step": len(reasoning_path) + 1,
                                    "from": s.entity_name,
                                    "to": "",
                                    "via": f"traversal:{s.relation_name}" if s.relation_name else "traversal",
                                    "relation_label": s.relation_label,
                                    "confidence": s.confidence,
                                })
                        # Enrich retrieval query with terminal entity names
                        terminal_names = trav["terminal_names"]
                        if terminal_names:
                            enhanced_question = f"{enhanced_question} [related: {', '.join(terminal_names[:5])}]"
                        # Cross-domain lookup via ShardedGraphIndex
                        if terminal_names:
                            try:
                                from core.harness.ontology_engine.engine import get_sharded_graph
                                sharded = get_sharded_graph()
                                for tname in terminal_names[:2]:
                                    cross = sharded.cross_domain_neighbors(
                                        tname, primary_domain=domain_id, allow_cross=False
                                    )
                                    min_cross = domain_config.get("min_cross_results", 3)
                                    if not cross or len(cross.get(domain_id, [])) < min_cross:
                                        cross = sharded.cross_domain_neighbors(
                                            tname,
                                            domains=list(set([domain_id] + router.fallback_domains())),
                                            primary_domain=domain_id,
                                            allow_cross=True,
                                        )
                                        reasoning_path.append({
                                            "step": len(reasoning_path) + 1,
                                            "from": tname,
                                            "to": "",
                                            "via": f"cross_domain_fallback:{router.fallback_domains()}",
                                            "relation_label": "降级跨域查询",
                                            "confidence": 0.6,
                                        })
                                    for did, neighbors in cross.items():
                                        if did != domain_id and neighbors:
                                            reasoning_path.append({
                                                "step": len(reasoning_path) + 1,
                                                "from": tname,
                                                "to": ", ".join(neighbors[:3]),
                                                "via": f"cross_domain:{did}",
                                                "relation_label": f"跨域关联({did})",
                                                "confidence": 0.7,
                                            })
                            except Exception as e:
                                logging.debug(str(e), exc_info=True)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

            # ── Semantic cache check (L1+L2+L3) ──
            try:
                from core.harness.knowledge.semantic_cache_hook import try_cache_hit
                cached = await try_cache_hit(enhanced_question, domain_id)
                if cached:
                    _trace("缓存命中", f"L{cached.get('level', '?')} cache",
                           cache_level=cached.get("level", ""))
                    return AgentResult(
                        success=True,
                        output={"answer": cached["answer"],
                                "citations": cached.get("citations", []), "items": [],
                                "scope_applied": scope, "strategy": "cache_hit",
                                "skills_used": [], "turn_summary": "",
                                "intent": intent, "mode": "cache", "analysis": analysis,
                                "retrieval_policy": retrieval_policy, "answer_strategy": answer_strategy,
                                "reasoning_path": reasoning_path,
                                "pipeline_trace": pipeline_trace,
                                "quality": "cached"},
                        metadata={"intent": intent, "strategy": "cache_hit", "cache_level": cached.get("level", ""),
                                   "doc_count": len(doc_ids)},
                    )
            except Exception as e:
                logging.debug(str(e), exc_info=True)

            # ── Retrieve document content (ontology-first, FTS5 fallback) ──
            retrieved_docs: str = ""
            citations: list = []
            try:
                if ontology_class_uri:
                    from core.harness.knowledge.orchestrated_retrieval import ontology_first_retrieve
                    retrieved_docs, citations = await ontology_first_retrieve(
                        enhanced_question,
                        ontology_class_uri,
                        domain_id=domain_id,
                        collection_id=collection_id,
                        top_k=int(retrieval_policy.get("top_k") or options.get("top_k") or 8),
                    )
                # ── CRAG: Quality gate — if retrieval is weak, try KB fallback ──
                if not retrieved_docs or len(retrieved_docs or "") < 100:
                    # Fallback: FTS5 + keyword search
                    from core.api.facades.kb_facade import kb_retrieve
                    results = kb_retrieve(
                        query=enhanced_question,
                        doc_ids=doc_ids,
                        collection_id=collection_id,
                        tenant_id=tenant_id,
                        top_k=int(retrieval_policy.get("top_k") or options.get("top_k") or 8),
                    )
                    if results:
                        parts = []
                        for r in results:
                            loc = ""
                            if r.get("start_s") is not None:
                                loc = f"[{r['start_s']:.0f}s] "
                            elif r.get("page_idx"):
                                loc = f"[p{r['page_idx']}] "
                            parts.append(f"{loc}{r['text']}")
                        retrieved_docs = "\n\n---\n\n".join(parts)
                        citations = []
                        for r in results:
                            ref = f"[doc:{r['doc_id'][:8]}]"
                            if r.get("start_s") is not None:
                                ref += f" [{r['start_s']:.0f}s-{r.get('end_s', 0):.0f}s]"
                            elif r.get("page_idx"):
                                ref += f" [p{r['page_idx']}]"
                            citations.append({"source": ref, "text": r["text"][:200]})

                # ── CRAG: Reroute via HyDE if still empty ──
                if not retrieved_docs or len(retrieved_docs or "") < 50:
                    try:
                        from core.harness.knowledge.hyde_expander import hyde_retrieve
                        hyde_docs, hyde_citations = await hyde_retrieve(
                            question,
                            wiki_collection_ids=[router.resolve_collection(domain_id)] if domain_id else [collection_id] if collection_id else None,
                            top_k=int(retrieval_policy.get("top_k") or options.get("top_k") or 8),
                        )
                        if hyde_docs:
                            retrieved_docs = hyde_docs
                            citations = hyde_citations
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            _trace("多路检索", f"检索到 {len(retrieved_docs)} 字符", sources=len(citations) if citations else 0)
            if retrieved_docs:
                skill_params["doc_content"] = retrieved_docs

            # ── Graph context: inject structured graph knowledge ──
            graph_context = ""
            try:
                from core.harness.syscalls.graph import sys_graph_query
                gq = await sys_graph_query("", operation="stats", domain_id=domain_id)
                if gq.get("success") and gq.get("data", {}).get("nodes", 0) > 0:
                    graph_context = f"\n[知识图谱摘要] {gq['result']}\n"
                    # Also get top classes
                    gq2 = await sys_graph_query("", operation="classes", domain_id=domain_id)
                    if gq2.get("success"):
                        graph_context += f"{gq2['result']}\n"
            except Exception:
                pass

            # Compress retrieved docs to fit model context window
            if retrieved_docs:
                from core.harness.knowledge.doc_compressor import compress_retrieved_docs
                model_name = best_model_for_purpose("chat")
                retrieved_docs = compress_retrieved_docs(retrieved_docs, model_name=model_name)

            # ── Hallucination check helper (lazy-import, best-effort) ──
            async def _check_hallucination(answer_text: str, current_quality: str):
                """Run HallucinationTracker.evaluate() to fact-check answer against citations.
                Returns (updated_quality, hallucination_meta_dict). Never fails the main path."""
                try:
                    from core.harness.evaluation.hallucination_tracker import get_hallucination_tracker
                    tracker = get_hallucination_tracker()
                    report = await tracker.evaluate(
                        question=enhanced_question,
                        answer=str(answer_text)[:5000],
                        retrieved_context=[{"text": c.get("text", str(c)[:300])} for c in (citations or [])[:10]],
                        run_id=str(run_id or ""),
                        domain_id=str(domain_id or "default"),
                    )
                    meta = {
                        "hallucination_risk": round(report.hallucination_risk, 3),
                        "faithfulness": round(report.faithfulness_score, 3),
                        "claims_supported": f"{report.supported_claims}/{report.total_claims}",
                        "quality_flag": report.quality_flag,
                    }
                    if report.hallucination_risk > 0.5:
                        return "low_evidence", meta
                    elif report.hallucination_risk > 0.2 and current_quality == "ok":
                        return "needs_review", meta
                    return current_quality, meta
                except Exception:
                    return current_quality, {}

            # ── Path A: Domain Skill execution (config-driven, opt-in per domain) ──
            if (retrieved_docs and ontology_mapping
                and domain_config.get("domain_skill_enabled", False)):
                from core.apps.skills.registry import get_skill_registry
                registry = get_skill_registry()
                domain_skills = [s for s in registry.list_all()
                                 if s.metadata.get("domain_id") == domain_id]
                if domain_skills:
                    skill_name = domain_skills[0].name
                    skill = registry.get(skill_name)
                    if skill:
                        skill_params["_domain_context"] = json.dumps(
                            {"domain_id": domain_id, "ontology_mapping": ontology_mapping,
                             "matched_classes": ontology_mapping.get("matched_classes", [])[:3]},
                            ensure_ascii=False)
                        response = await sys_skill_call(skill, skill_params, user_id=user_id, session_id=session_id)
                        if response.success:
                            out = dict(response.output or {})
                            answer = str(out.get("answer") or "").strip()
                            if answer:
                                citations = list(out.get("citations") or [])
                                turn_summary = _build_turn_summary(question, answer)
                                strategy, skills_used = _resolve_strategy(
                                    doc_count=len(doc_ids), intent=intent,
                                    route=str(retrieval_policy.get("route") or ""),
                                    default_skill=skill_name)
                                quality = self_review(answer, citations, reasoning_path)
                                quality, hallucination_meta = await _check_hallucination(answer, quality)
                                rag_diagnosis = diagnose_rag_quality(
                                    faithfulness=hallucination_meta.get("faithfulness", 0),
                                    hallucination_risk=hallucination_meta.get("hallucination_risk", 0),
                                    quality=quality, retrieved_count=len(citations))
                                return AgentResult(
                                    success=True,
                                    output={"answer": answer, "citations": citations, "items": [],
                                            "scope_applied": scope, "strategy": "domain_skill",
                                            "skills_used": [skill_name], "turn_summary": turn_summary,
                                            "intent": intent, "mode": "", "analysis": analysis,
                                            "retrieval_policy": retrieval_policy, "answer_strategy": answer_strategy,
                                            "reasoning_path": reasoning_path, "pipeline_trace": pipeline_trace,
                                            "quality": quality, "hallucination": hallucination_meta,
                                            "rag_diagnosis": rag_diagnosis},
                                    metadata={"intent": intent, "strategy": "domain_skill", "domain": domain_id,
                                              "skill": skill_name, "doc_count": len(doc_ids)})

            # ── Direct answer: if doc_content retrieved, use LLM (with streaming if available) ──
            if retrieved_docs:
                try:
                    # Check for streaming queue in context
                    stream_queue = vars0.get("_stream_queue")
                    if stream_queue is not None:
                        # Stream mode: push chunks to queue, collect full answer
                        from core.harness.generation.answer_generator import generate_stream_answer, build_rag_user_message
                        system_msgs = _assemble_chat_system_msgs(domain_config, run_context)
                        user_msg = build_rag_user_message(retrieved_docs, enhanced_question, graph_context=graph_context)
                        answer, trace = await generate_stream_answer(system_msgs, user_msg, stream_queue)
                        if trace.get("model_name"):
                            _complexity = vars0.get("_query_complexity", "unknown")
                            logging.getLogger("aiplat.cost").info(
                                f"[CostTrace] model={trace['model_name']} complexity={_complexity} "
                                f"input_tok_est={trace['input_tok_est']} stream=true max_tokens={trace['max_tokens']}"
                            )
                    else:
                        from core.harness.generation.answer_generator import generate_answer, build_rag_user_message
                        sys_msgs = _assemble_chat_system_msgs(domain_config, run_context)
                        user_msg = build_rag_user_message(retrieved_docs, enhanced_question, graph_context=graph_context)
                        answer, trace = await generate_answer(sys_msgs, user_msg)
                        if trace.get("model_name"):
                            _complexity = vars0.get("_query_complexity", "unknown")
                            logging.getLogger("aiplat.cost").info(
                                f"[CostTrace] model={trace['model_name']} complexity={_complexity} "
                                f"input_tok_est={trace['input_tok_est']} max_tokens={trace['max_tokens']}"
                            )
                        quality = self_review(answer, citations, reasoning_path)
                        # Self-RAG: auto-retry on low_evidence via HyDE reroute
                        if quality == "low_evidence" and not retrieved_docs:
                            try:
                                from core.harness.knowledge.hyde_expander import hyde_retrieve
                                hyde_docs, hyde_citations = await hyde_retrieve(
                                    question,
                                    wiki_collection_ids=[router.resolve_collection(domain_id)] if domain_id else [collection_id] if collection_id else None,
                                    top_k=int(retrieval_policy.get("top_k") or options.get("top_k") or 8),
                                )
                                if hyde_docs:
                                    retrieved_docs = hyde_docs
                                    citations = hyde_citations
                                    # Re-generate answer with HyDE results
                                    hyde_sys_msgs = _assemble_chat_system_msgs(domain_config, run_context)
                                    hyde_user = build_rag_user_message(retrieved_docs, enhanced_question, graph_context=graph_context)
                                    hyde_answer, _ = await generate_answer(hyde_sys_msgs, hyde_user)
                                    answer = hyde_answer
                            except Exception as e:
                                logging.debug(str(e), exc_info=True)
                        quality = self_review(answer, citations, reasoning_path)
                        _trace("质量评估", f"Self-RAG: {quality}", quality=quality)

                        quality, hallucination_meta = await _check_hallucination(answer, quality)
                        rag_diagnosis = diagnose_rag_quality(
                            faithfulness=hallucination_meta.get("faithfulness", 0),
                            hallucination_risk=hallucination_meta.get("hallucination_risk", 0),
                            quality=quality,
                            retrieved_count=len(citations),
                        )

                        return AgentResult(
                            success=True,
                            output={"answer": answer, "citations": citations, "items": [],
                                    "scope_applied": scope, "strategy": "direct_retrieve",
                                    "skills_used": ["sys_kb_retrieve"], "turn_summary": _build_turn_summary(question, answer),
                                    "intent": intent, "mode": "", "analysis": analysis,
                                    "retrieval_policy": retrieval_policy, "answer_strategy": answer_strategy,
                                    "reasoning_path": reasoning_path,
                                    "pipeline_trace": pipeline_trace,
                                    "quality": quality,
                                    "hallucination": hallucination_meta,
                                    "rag_diagnosis": rag_diagnosis},
                            metadata={"intent": intent, "strategy": "direct_retrieve", "doc_count": len(doc_ids)},
                        )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

            registry = get_skill_registry()
            skill = registry.get(skill_name)
            if not skill:
                return AgentResult(success=False, error=f"skill_not_found:{skill_name}")

            # Ensure skill has LLM adapter (prompt-mode skills need it)
            if hasattr(skill, '_model') and skill._model is None:
                try:
                    from core.server import _inject_model_into_skill
                    _inject_model_into_skill(skill)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

            # Fast path: direct sys_skill_call (single LLM invocation, no ReAct loop overhead)
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

            quality = self_review(answer, citations, reasoning_path)
            quality, hallucination_meta = await _check_hallucination(answer, quality)
            rag_diagnosis = diagnose_rag_quality(
                faithfulness=hallucination_meta.get("faithfulness", 0),
                hallucination_risk=hallucination_meta.get("hallucination_risk", 0),
                quality=quality,
                retrieved_count=len(citations),
            )

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
                    "reasoning_path": reasoning_path,
                    "pipeline_trace": pipeline_trace,
                    "quality": quality,
                    "hallucination": hallucination_meta,
                    "rag_diagnosis": rag_diagnosis,
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
                    # Phase C6: latency baseline + routing cost breakdown
                    "latency_ms": int((time.time() - _t0) * 1000),
                    "cost_routing": {
                        "rag_est_tokens": _cost.rag_est_tokens,
                        "full_est_tokens": _cost.full_est_tokens,
                        "recommendation": _cost.recommendation,
                        "cache_saving": _cost.cache_saving,
                        "cache_available": _cost.cache_saving > 0,
                    },
                    "fallback_chain": [
                        t for t in pipeline_trace
                        if t.get("phase") in ("检索质量门", "CRAG", "HyDE", "FTS5 fallback", "缓存命中")
                    ],
                },
            )
            # Phase C6: record latency for aggregate P50/P95 stats
            from core.harness.knowledge.cost_estimator import record_latency as _rec_lat
            _rec_lat(_cost.recommendation, (time.time() - _t0) * 1000)
        except Exception as e:
            self._status = AgentStatus.ERROR
            return AgentResult(success=False, error=str(e), metadata={"exception": type(e).__name__})
        finally:
            if self._status != AgentStatus.ERROR:
                self._status = AgentStatus.COMPLETED


def create_materials_chat_agent(config: AgentConfig, **kwargs) -> MaterialsChatAgent:
    return MaterialsChatAgent(config=config, **kwargs)
