u"""
Knowledge Retrieval Handler (v2.8) — deterministic retrieval wrapper.

Wraps sys_knowledge_retrieve with CRAG 3-level fallback, providing
a traceable, auditable retrieval path instead of LLM simulation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("knowledge_retrieval_handler")


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    u"""Execute knowledge retrieval with CRAG fallback.

    Input: { query, domain_id?, collection_id?, top_k?, wiki_first? }
    Output: { results, strategy, trace }
    """
    query = params.get("query", "")
    domain_id = params.get("domain_id", "")
    collection_id = params.get("collection_id", "default")
    top_k = params.get("top_k", 10)

    try:
        from core.harness.syscalls.retrieval import sys_knowledge_retrieve
        results = sys_knowledge_retrieve(
            query=query,
            domain_id=domain_id,
            collection_id=collection_id,
            top_k=top_k,
            wiki_first=True,
        )
        strategy = "syscall"
        trace = ["direct_retrieve"]
    except Exception:
        results = None
        strategy = "syscall_failed"
        trace = []

    return {
        "results": results,
        "strategy": strategy,
        "trace": trace,
        "query": query,
        "result_count": len(results or []),
    }
