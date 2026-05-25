"""
RAG Agent Module

Provides Retrieval-Augmented Generation agent implementation.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

from .base import BaseAgent, AgentMetadata
from ...harness.interfaces import AgentResult, AgentConfig, AgentContext
from ...harness.knowledge import KnowledgeRetriever, KnowledgeResult


@dataclass
class RAGConfig:
    """RAG agent configuration"""
    top_k: int = 5
    min_relevance: float = 0.5
    max_context_length: int = 4000
    chunk_size: int = 500
    rerank: bool = True
    rerank_top_k: int = 3


class RAGAgent(BaseAgent):
    """
    Retrieval-Augmented Generation Agent
    
    Combines retrieval from knowledge base with LLM generation.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        rag_config: Optional[RAGConfig] = None,
        retriever: Optional[KnowledgeRetriever] = None,
        model: Optional[Any] = None,
    ):
        super().__init__(config, model=model)
        self._rag_config = rag_config or RAGConfig()
        self._retriever = retriever or self._create_retriever()
        self._name = "rag_agent"
        self._description = "Retrieval-Augmented Generation Agent"
        self._metadata = AgentMetadata(
            name="rag_agent",
            description="Retrieval-Augmented Generation Agent",
            version="1.0.0",
            capabilities=["retrieval", "generation", "knowledge_qa"],
            supported_loop_types=["rag", "retrieval_first"],
        )

    def _create_retriever(self) -> KnowledgeRetriever:
        import os
        backend = os.getenv("AIPLAT_VECTOR_BACKEND", "")
        common_kw = dict(
            retrieval_strategy="hybrid",
            rerank_enabled=True,
            rerank_method="multi_factor",
            rerank_top_k=self._rag_config.rerank_top_k,
            quality_gate_enabled=True,
        )
        if not backend:
            return KnowledgeRetriever(**common_kw)
        try:
            from ...harness.knowledge import create_vector_retriever
            retriever = create_vector_retriever(backend=backend)
            for k, v in common_kw.items():
                setattr(retriever, f"_{k}", v)
            return retriever
        except Exception:
            return KnowledgeRetriever(**common_kw)
    
    @property
    def metadata(self) -> AgentMetadata:
        return self._metadata
    
    async def execute(
        self,
        context: AgentContext,
        params: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        """Execute via shared ReAct loop (§5.22: delegates to BaseAgent).

        Retrieval is done here (pre-loop), then the loop handles generation
        using the retrieved context injected into context.variables.
        """
        params = params or {}
        query = params.get("query") or context.variables.get("query", "")
        if not query and context.messages:
            query = context.messages[-1].get("content", "")

        if not query:
            return AgentResult(success=False, output=None, error="No query provided", metadata={"agent": self._name})

        try:
            retrieval_results = await self._retrieve(query)
            context_text = self._build_context(retrieval_results)
            # Inject retrieved context so the shared loop can use it
            context.variables["_retrieved_context"] = context_text
            context.variables["_rag_query"] = query
            context.variables["_rag_sources"] = [r.entry.id for r in retrieval_results]

            result = await super().execute(context)
            if result.metadata is None:
                result.metadata = {}
            result.metadata.update({
                "agent": self._name,
                "query": query,
                "context_length": len(context_text),
                "sources": [r.entry.id for r in retrieval_results],
            })
            return result
        except Exception as e:
            return AgentResult(success=False, output=None, error=str(e), metadata={"agent": self._name})
    
    async def _retrieve(self, query: str) -> List[KnowledgeResult]:
        results = await self._retriever.search(query, limit=self._rag_config.top_k)
        if self._rag_config.rerank:
            results = results[:self._rag_config.rerank_top_k]
        return results
    
    
    def _build_context(self, results: List[KnowledgeResult]) -> str:
        context_parts = []
        current_length = 0
        
        for result in results:
            content = result.entry.content
            if current_length + len(content) > self._rag_config.max_context_length:
                break
            
            if result.entry.title:
                context_parts.append(f"[{result.entry.title}]")
            context_parts.append(content)
            context_parts.append("")
            
            current_length += len(content) + len(result.entry.title or "") + 10
        
        return "\n".join(context_parts)
    
    def _build_prompt(self, query: str, context: str) -> str:
        return f"""Based on the following context, please answer the question.

Context:
{context}

Question: {query}

Please provide a comprehensive answer based on the context above."""

    async def add_knowledge(
        self,
        content: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        from ...harness.knowledge import KnowledgeEntry, KnowledgeType, KnowledgeSource, KnowledgeMetadata
        
        import uuid
        entry = KnowledgeEntry(
            id=str(uuid.uuid4()),
            type=KnowledgeType.DOCUMENT,
            content=content,
            title=title,
            metadata=KnowledgeMetadata(
                source=KnowledgeSource.USER,
                tags=tags or [],
            ),
        )
        
        if hasattr(self._retriever, "_retriever"):
            retriever = self._retriever._retriever
            if hasattr(retriever, "add"):
                await retriever.add(entry)
            return entry.id
        
        return ""


def create_rag_agent(
    config: Optional[AgentConfig] = None,
    rag_config: Optional[RAGConfig] = None,
    model: Optional[Any] = None,
) -> RAGAgent:
    config = config or AgentConfig(name="rag_agent")
    return RAGAgent(config, rag_config, model=model)


__all__ = [
    "RAGConfig",
    "RAGAgent",
    "create_rag_agent",
]
