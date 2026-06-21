from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

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


def _self_review(answer: str, citations: list, reasoning_path: list) -> str:
    """Self-RAG lite: post-generation quality check.
    
    Returns quality flag: "ok" | "needs_review" | "low_evidence"
    """
    if not answer or len(answer) < 20:
        return "low_evidence"
    has_evidence = bool(citations)
    has_reasoning = len(reasoning_path) >= 2
    if not has_evidence and not has_reasoning:
        return "low_evidence"
    if not has_evidence:
        return "needs_review"
    return "ok"


def _sanitize_query(query: str) -> str:
    """§5.63: Strip control tokens and truncate for safety."""
    import re
    # Remove model control tokens
    q = re.sub(r'<\|[^|]+\|>', '', query)
    q = re.sub(r'```[\s\S]*?```', '', q)  # Remove code blocks
    q = q.replace('\\', '')
    return q.strip()[:1000]


def _enforce_scope(collection_id: str, domain_id: str) -> bool:
    """§5.62: Verify scope is set — no unscoped full-db scans."""
    return bool(collection_id and collection_id != "default") or bool(domain_id != "default")


def _build_turn_summary(question: str, answer: str) -> str:
    q = str(question or "").strip()
    a = str(answer or "").strip()
    if not a:
        return f"用户提问：{q}"
    return f"用户提问：{q}；本轮回答要点：{a[:160]}"


def _load_doc_kinds(*, tenant_id: str, doc_ids: List[str]) -> List[str]:
    return get_kb_load_doc_kinds_fn()(tenant_id=tenant_id, doc_ids=doc_ids)


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
        import asyncio
        try:
            return await asyncio.wait_for(self._execute_impl(context), timeout=120)
        except TimeoutError:
            return AgentResult(success=False, error="timeout", metadata={"reason": "execution exceeded 120s"})

    async def _execute_impl(self, context: AgentContext) -> AgentResult:
        try:
            _t0 = time.time()
            pipeline_trace: list = []  # [{phase, latency_ms, detail, ...}]
            def _trace(phase: str, detail: str, **meta):
                t = int((time.time() - _t0) * 1000)
                entry = {"phase": phase, "detail": detail, "total_ms": t}
                entry.update(meta)
                pipeline_trace.append(entry)

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

            # §5.63: Query sanitization
            question = _sanitize_query(question)
            # §5.62: Scope enforcement
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
            except Exception:
                pass
            retrieval_policy = choose_retrieval_policy(analysis=analysis, scope=scope, doc_kinds=doc_kinds)
            answer_strategy = choose_answer_strategy(analysis=analysis, retrieval_policy=retrieval_policy)

            # ── Domain routing (multi-domain support) ──
            from core.harness.knowledge.domain_router import DomainRouter
            router = DomainRouter()
            domain_id = router.classify(enhanced_question)
            domain_config = router.domain_config(domain_id)
            _trace("域路由", f"→ {domain_id}", domain_id=domain_id)

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
            try:
                from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology
                onto_mapping = map_query_to_ontology(enhanced_question, domain_id=domain_id, collection_id=collection_id)
                if onto_mapping:
                    ontology_mapping = onto_mapping
                    matched = onto_mapping.get("matched_classes") or []
                    if matched and matched[0].get("score", 0) >= 0.8:
                        ontology_class_uri = matched[0].get("uri", "")
            except Exception:
                pass
            _trace("本体感知", f"匹配类: {', '.join((m.get('label','') for m in (ontology_mapping.get('matched_classes',[]) if ontology_mapping else [])[:3])) or '无'}",
                   matched_count=len(ontology_mapping.get("matched_classes", [])) if ontology_mapping else 0)

            # ── Build reasoning path ──
            reasoning_path: List[Dict[str, Any]] = []
            if ontology_class_uri and ontology_mapping:
                matched_name = (ontology_mapping.get("matched_classes") or [{}])[0].get("label", "")
                reasoning_path.append({
                    "step": 1,
                    "from": question[:60],
                    "to": matched_name or ontology_class_uri,
                    "via": "intent_classify",
                    "confidence": (ontology_mapping.get("matched_classes") or [{}])[0].get("score", 0),
                })
                # Try graph traversal to extend path (multi-entity SAG-style)
                try:
                    from core.harness.ontology_engine.graph_index import GraphIndex
                    from core.harness.ontology_engine.graph_traversal import traverse_multi as graph_traverse_multi
                    from core.harness.knowledge.domain_router import DomainRouter
                    router = DomainRouter()
                    domain_id = router.resolve(collection_id)
                    graph = GraphIndex.load(domain_id)
                    if len(graph) > 0:
                        # Collect entity names from ALL matched classes
                        start_entities = []
                        for mc in (ontology_mapping.get("matched_classes") or [])[:3]:
                            label = mc.get("label", "")
                            if label:
                                node = graph.find_by_name(label)
                                if node:
                                    start_entities.append(node.entity_id)
                                else:
                                    start_entities.append(label)
                        # Multi-entity traversal (SAG-style local subgraph expansion)
                        trav = graph_traverse_multi(start_entities, graph, max_hops=2)
                        for tpath in trav.paths[:5]:
                            for s in tpath.steps[1:]:
                                reasoning_path.append({
                                    "step": len(reasoning_path) + 1,
                                    "from": s.entity_name,
                                    "to": "",
                                    "via": f"traversal:{s.relation_name}" if s.relation_name else "traversal",
                                    "relation_label": s.relation_label,
                                    "confidence": s.confidence,
                                })
                        # Enrich retrieval query with terminal entity names (structure → semantic)
                        terminal_names = [t.get("entity_name", "") for t in trav.terminal_entities[:5] if t.get("entity_name")]
                        if terminal_names:
                            enhanced_question = f"{enhanced_question} [related: {', '.join(terminal_names[:5])}]"
                        # Cross-domain lookup via ShardedGraphIndex (domain-scoped + degradation)
                        if terminal_names:
                            try:
                                from core.harness.ontology_engine.engine import get_sharded_graph
                                sharded = get_sharded_graph()
                                for tname in terminal_names[:2]:
                                    # Primary: domain-scoped only
                                    cross = sharded.cross_domain_neighbors(
                                        tname, primary_domain=domain_id, allow_cross=False
                                    )
                                    min_cross = domain_config.get("min_cross_results", 3)
                                    if not cross or len(cross.get(domain_id, [])) < min_cross:
                                        # Degradation: fallback to supplementary domains
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
                                            "relation_label": f"降级跨域查询",
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
                            except Exception:
                                pass
                except Exception:
                    pass

            reasoning_path.append({
                "step": len(reasoning_path) + 1,
                "from": "knowledge_base",
                "to": "answer",
                "via": "knowledge_retrieve",
            })

            # ── Retrieve document content (ontology-first, FTS5 fallback) ──
            retrieved_docs: str = ""
            citations: list = []
            try:
                if ontology_class_uri:
                    # Ontology-aware path: filter by target class
                    from core.harness.syscalls.retrieval import sys_knowledge_retrieve
                    # Related class tolerance: also retrieve neighbor classes via graph
                    target_classes = [ontology_class_uri]
                    try:
                        from core.harness.ontology_engine.graph_index import GraphIndex
                        g = GraphIndex.load("ai-knowledge")
                        if len(g) > 0:
                            short = ontology_class_uri.rsplit("/", 1)[-1] if "/" in ontology_class_uri else ontology_class_uri
                            node = g.find_by_name(short)
                            if node:
                                neighbors = g.get_neighbors(node.entity_id, direction="both")
                                for n in neighbors[:3]:
                                    if n.class_name and n.class_name not in target_classes:
                                        target_classes.append(n.uri if hasattr(n, 'uri') else n.class_name)
                    except Exception:
                        pass
                    # Multi-class retrieval: search each target class then merge
                    import asyncio
                    retrieval_tasks = []
                    for tc in target_classes[:3]:
                        retrieval_tasks.append(
                            sys_knowledge_retrieve(
                                query=enhanced_question,
                                wiki_first=True,
                                wiki_collection_ids=[router.resolve_collection(domain_id)] if domain_id else [collection_id] if collection_id else None,
                                target_class=tc,
                                expand_subclasses=True,
                                top_k=int(retrieval_policy.get("top_k") or options.get("top_k") or 8),
                            )
                        )
                    all_batches = await asyncio.gather(*retrieval_tasks, return_exceptions=True)
                    # Merge & dedup by title
                    seen_titles = set()
                    merged = []
                    for batch in all_batches:
                        if isinstance(batch, Exception):
                            continue
                        for r in batch:
                            key = r.get("title", r.get("source", str(r)[:80]))
                            if key not in seen_titles:
                                seen_titles.add(key)
                                merged.append(r)
                    wiki_results = merged
                    if wiki_results:
                        retrieved_docs = "\n\n---\n\n".join(
                            f"[{r.get('source', 'wiki')}] {r.get('content', str(r))[:2000]}"
                            for r in wiki_results
                        )
                        citations = [
                            {"source": r.get("source", "wiki"), "text": str(r.get("content", ""))[:200]}
                            for r in wiki_results
                        ]
                # ── CRAG: Quality gate — if retrieval is weak, try HyDE reroute ──
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
                        from core.harness.syscalls.llm import sys_llm_generate
                        hyde_prompt = _resolve("hyde-generator", question=question)
                        hyde_resp = await sys_llm_generate(
                            None,
                            [{"role": "user", "content": hyde_prompt}],
                            model_name=best_model_for_purpose("chat"),
                            temperature=0.3, max_tokens=200,
                        )
                        hyde_answer = getattr(hyde_resp, 'content', '') or str(hyde_resp)
                        if hyde_answer and len(hyde_answer.strip()) > 10:
                            # Retry with HyDE-generated query
                            hyde_results = await sys_knowledge_retrieve(
                                query=hyde_answer.strip()[:300],
                                wiki_first=True,
                                wiki_collection_ids=[router.resolve_collection(domain_id)] if domain_id else [collection_id] if collection_id else None,
                                top_k=int(retrieval_policy.get("top_k") or options.get("top_k") or 8),
                            )
                            if hyde_results:
                                retrieved_docs = "\n\n---\n\n".join(
                                    f"[HyDE:{r.get('source', 'wiki')}] {r.get('content', str(r))[:2000]}"
                                    for r in hyde_results
                                )
                                citations = [
                                    {"source": f"HyDE:{r.get('source', 'wiki')}", "text": str(r.get("content", ""))[:200]}
                                    for r in hyde_results
                                ]
                    except Exception:
                        pass
            except Exception:
                pass
            _trace("多路检索", f"检索到 {len(retrieved_docs)} 字符", sources=len(citations) if citations else 0)
            if retrieved_docs:
                skill_params["doc_content"] = retrieved_docs

            # Compress retrieved docs to fit model context window
            if retrieved_docs:
                from core.harness.knowledge.doc_compressor import compress_retrieved_docs
                model_name = best_model_for_purpose("chat")
                retrieved_docs = compress_retrieved_docs(retrieved_docs, model_name=model_name)

            # ── Direct answer: if doc_content retrieved, use LLM (with streaming if available) ──
            if retrieved_docs:
                try:
                    # Check for streaming queue in context
                    stream_queue = vars0.get("_stream_queue")
                    if stream_queue is not None:
                        # Stream mode: push chunks to queue, collect full answer
                        from core.harness.syscalls.llm import sys_llm_generate_stream
                        system_msgs = []
                        prompt_id = domain_config.get("system_prompt_id")
                        if prompt_id:
                            system_msgs.append({"role": "system", "content": _resolve(prompt_id)})
                        system_msgs.append({"role": "system", "content": _resolve("kb-chat-system-role")})
                        answer_parts = []
                        async for chunk in sys_llm_generate_stream(
                            None,
                            system_msgs + [
                                {"role": "user", "content": f"文档内容：\n{retrieved_docs}\n\n用户问题：{enhanced_question}\n\n请回答："},
                            ],
                            model_name=best_model_for_purpose("chat"),  # noqa: model-legacy
                            temperature=0.3,
                            max_tokens=2000,
                        ):
                            if chunk:
                                answer_parts.append(chunk)
                                try:
                                    stream_queue.append(chunk)
                                except Exception:
                                    pass
                        answer = "".join(answer_parts).strip()
                    else:
                        from core.harness.syscalls.llm import sys_llm_generate
                        sys_msgs = []
                        prompt_id = domain_config.get("system_prompt_id")
                        if prompt_id:
                            sys_msgs.append({"role": "system", "content": _resolve(prompt_id)})
                        sys_msgs.append({"role": "system", "content": _resolve("kb-chat-system-role")})
                        resp = await sys_llm_generate(
                            None,
                            sys_msgs + [
                                {"role": "user", "content": f"文档内容：\n{retrieved_docs}\n\n用户问题：{enhanced_question}\n\n请回答："},
                            ],
                            model_name=best_model_for_purpose("chat"),  # noqa: model-legacy
                            temperature=0.3,
                            max_tokens=2000,
                        )
                        text = getattr(resp, 'content', '') or str(resp)
                        answer = text.strip() if text and len(text) > 5 else ""
                        if convo is not None and answer:
                            try:
                                await convo.append_conversation_assistant_message(
                                    tenant_id=tenant_id, session_id=session_id, user_id=user_id,
                                    content=answer, citations=citations, turn_summary=_build_turn_summary(question, answer),
                                    strategy="direct_retrieve", mode="", intent=intent,
                                    skills_used=["sys_kb_retrieve"],
                                    analysis=analysis, retrieval_policy=retrieval_policy,
                                    answer_strategy=answer_strategy, run_id=run_id,
                                )
                            except Exception:
                                pass
                        quality = _self_review(answer, citations, reasoning_path)
                        # Self-RAG: auto-retry on low_evidence via HyDE reroute
                        if quality == "low_evidence" and not retrieved_docs:
                            try:
                                from core.harness.syscalls.llm import sys_llm_generate
                                hyde_prompt = _resolve("hyde-generator", question=question)
                                hyde_resp = await sys_llm_generate(
                                    None, [{"role": "user", "content": hyde_prompt}],
                                    model_name=best_model_for_purpose("chat"),
                                    temperature=0.3, max_tokens=200,
                                )
                                hyde_answer = getattr(hyde_resp, 'content', '') or str(hyde_resp)
                                if hyde_answer and len(hyde_answer.strip()) > 10:
                                    hyde_results = await sys_knowledge_retrieve(
                                        query=hyde_answer.strip()[:300],
                                        wiki_first=True,
                                        wiki_collection_ids=[router.resolve_collection(domain_id)] if domain_id else [collection_id] if collection_id else None,
                                        top_k=int(retrieval_policy.get("top_k") or options.get("top_k") or 8),
                                    )
                                    if hyde_results:
                                        retrieved_docs = "\n\n---\n\n".join(
                                            f"[HyDE:{r.get('source', 'wiki')}] {r.get('content', str(r))[:2000]}"
                                            for r in hyde_results
                                        )
                                        citations = [
                                            {"source": f"HyDE:{r.get('source', 'wiki')}", "text": str(r.get("content", ""))[:200]}
                                            for r in hyde_results
                                        ]
                                        # Re-generate answer with HyDE results
                                        hyde_sys_msgs = []
                                        prompt_id = domain_config.get("system_prompt_id")
                                        if prompt_id:
                                            hyde_sys_msgs.append({"role": "system", "content": _resolve(prompt_id)})
                                        hyde_sys_msgs.append({"role": "system", "content": _resolve("kb-chat-system-role")})
                                        resp = await sys_llm_generate(
                                            None,
                                            hyde_sys_msgs + [{"role": "user", "content": f"文档内容：\n{retrieved_docs}\n\n用户问题：{enhanced_question}\n\n请回答："}],
                                            model_name=best_model_for_purpose("chat"),
                                            temperature=0.3, max_tokens=2000,
                                        )
                                        text = getattr(resp, 'content', '') or str(resp)
                                        answer = text.strip() if text and len(text) > 5 else ""
                            except Exception:
                                pass
                        quality = _self_review(answer, citations, reasoning_path)
                        _trace("质量评估", f"Self-RAG: {quality}", quality=quality)
                        return AgentResult(
                            success=True,
                            output={"answer": answer, "citations": citations, "items": [],
                                    "scope_applied": scope, "strategy": "direct_retrieve",
                                    "skills_used": ["sys_kb_retrieve"], "turn_summary": _build_turn_summary(question, answer),
                                    "intent": intent, "mode": "", "analysis": analysis,
                                    "retrieval_policy": retrieval_policy, "answer_strategy": answer_strategy,
                                    "reasoning_path": reasoning_path,
                                    "pipeline_trace": pipeline_trace,
                                    "quality": quality},
                            metadata={"intent": intent, "strategy": "direct_retrieve", "doc_count": len(doc_ids)},
                        )
                except Exception:
                    pass  # fall through to skill path

            registry = get_skill_registry()
            skill = registry.get(skill_name)
            if not skill:
                return AgentResult(success=False, error=f"skill_not_found:{skill_name}")

            # Ensure skill has LLM adapter (prompt-mode skills need it)
            if hasattr(skill, '_model') and skill._model is None:
                try:
                    from core.server import _inject_model_into_skill
                    _inject_model_into_skill(skill)
                except Exception:
                    pass

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

            # Bridge to MemoryManager for cross-session recall
            try:
                from core.harness.memory.manager import get_memory_manager
                mm = get_memory_manager(namespace=f"kb_{session_id}")
                await mm.save_interaction(question, answer, stability="high")
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
                    "reasoning_path": reasoning_path,
                    "pipeline_trace": pipeline_trace,
                    "quality": _self_review(answer, citations, reasoning_path),
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
