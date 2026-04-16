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
from ...harness.knowledge import KnowledgeRetriever, KnowledgeQuery, KnowledgeResult


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
        self._retriever = retriever or KnowledgeRetriever()
        self._name = "rag_agent"
        self._description = "Retrieval-Augmented Generation Agent"
        self._metadata = AgentMetadata(
            name="rag_agent",
            description="Retrieval-Augmented Generation Agent",
            version="1.0.0",
            capabilities=["retrieval", "generation", "knowledge_qa"],
            supported_loop_types=["rag", "retrieval_first"],
        )
    
    @property
    def metadata(self) -> AgentMetadata:
        return self._metadata
    
    async def execute(
        self,
        context: AgentContext,
        params: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        params = params or {}
        query = params.get("query") or context.variables.get("query", "")
        if not query and context.messages:
            query = context.messages[-1].get("content", "")
        
        if not query:
            return AgentResult(
                success=False,
                output=None,
                error="No query provided",
                metadata={"agent": self._name},
            )
        
        try:
            retrieval_results = await self._retrieve(query)
            context_text = self._build_context(retrieval_results)
            prompt = self._build_prompt(query, context_text)
            response = await self._generate(prompt, context)
            
            return AgentResult(
                success=True,
                output=response,
                metadata={
                    "agent": self._name,
                    "query": query,
                    "context_length": len(context_text),
                    "sources": [r.entry.id for r in retrieval_results],
                },
            )
        except Exception as e:
            return AgentResult(
                success=False,
                output=None,
                error=str(e),
                metadata={"agent": self._name},
            )
    
    async def _retrieve(self, query: str) -> List[KnowledgeResult]:
        knowledge_query = KnowledgeQuery(
            query=query,
            limit=self._rag_config.top_k,
            min_relevance=self._rag_config.min_relevance,
        )
        
        results = await self._retriever.search(query, limit=self._rag_config.top_k)
        
        if self._rag_config.rerank:
            results = self._rerank_results(query, results)
            results = results[:self._rag_config.rerank_top_k]
        
        return results
    
    def _rerank_results(
        self,
        query: str,
        results: List[KnowledgeResult],
    ) -> List[KnowledgeResult]:
        def relevance_score(result: KnowledgeResult) -> float:
            query_words = set(query.lower().split())
            content_words = set(result.entry.content.lower().split())
            overlap = len(query_words & content_words)
            return overlap / len(query_words) if query_words else 0
        
        sorted_results = sorted(
            results,
            key=lambda r: r.score + relevance_score(r) * 0.1,
            reverse=True,
        )
        return sorted_results
    
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

Please provide a comprehensive answer based on the context above. If the context doesn't contain enough information to answer the question, please say so."""
    
    async def _generate(
        self,
        prompt: str,
        context: AgentContext,
    ) -> str:
        if self._model is None:
            return "LLM model not configured. Please provide a valid LLM adapter."
        from ...harness.syscalls.llm import sys_llm_generate

        response = await sys_llm_generate(self._model, [{"role": "user", "content": prompt}])
        
        return response.content
    
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
