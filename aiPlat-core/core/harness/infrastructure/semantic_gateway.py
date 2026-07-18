u"""
Semantic Gateway — Agent 数据网关 (v2.6).

统一入口 for all Agent→system interactions: 
  DomainRouter.classify() → PolicyGate.check() → TermResolver → ContextAssemble

概念："Agent Data Gateway" = AI 调用的总闸门。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("semantic_gateway")


@dataclass
class GatewayRequest:
    action: str                 # "tool_call" | "skill_call" | "knowledge_retrieve" | "llm_generate"
    domain_id: str = ""         # domain hint (optional, will auto-classify)
    actor: Dict[str, Any] = field(default_factory=dict)   # {tenant_id, role, scopes}
    payload: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)  # {session_id, run_id, task}


@dataclass
class GatewayResponse:
    allowed: bool = True
    reason: str = ""
    domain_id: str = ""
    domain_config: Dict[str, Any] = field(default_factory=dict)
    retrieval_strategy: str = "ontology_first"
    injected_context: Dict[str, Any] = field(default_factory=dict)
    rate_limit: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


async def route(request: GatewayRequest) -> GatewayResponse:
    u"""Unified gateway routing — the single entry point for all Agent→system calls."""
    t0 = time.time()
    response = GatewayResponse()

    # Step 1: Domain classification
    task = request.context.get("task", "") or request.payload.get("query", "")
    if task and not request.domain_id:
        try:
            from core.harness.knowledge.domain_router import DomainRouter
            router = DomainRouter()
            classified = router.classify(task)
            if classified and classified.get("domain_id"):
                response.domain_id = classified["domain_id"]
                response.domain_config = classified.get("config", {})
        except Exception as e:
            logger.debug("DomainRouter.classify failed: %s", e)

    if request.domain_id and not response.domain_id:
        response.domain_id = request.domain_id

    # Step 2: Policy check (delegated to existing PolicyGate in syscall layer)
    # This is an advisory pass — actual enforcement happens in sys_tool_call etc.

    # Step 3: Term disambiguation (if domain identified)
    if response.domain_id and task:
        try:
            from core.harness.knowledge.term_resolver import resolve_term
            for word in task.split():
                if len(word) >= 2:
                    resolved = resolve_term(word, domain_id=response.domain_id)
                    if resolved.get("same_name_ambiguity"):
                        response.injected_context.setdefault("ambiguous_terms", {})
                        response.injected_context["ambiguous_terms"][word] = resolved
        except Exception:
            pass

    # Step 4: Retrieval strategy selection
    if response.domain_config:
        mapping_mode = response.domain_config.get("ontology_mapping", "best_effort")
        response.retrieval_strategy = "ontology_first" if mapping_mode == "mandatory" else "fts5"

    # Step 5: Volume quota (placeholder for ticketing)
    response.rate_limit = {"remaining": -1, "reset": 0}

    response.allowed = True
    response.latency_ms = (time.time() - t0) * 1000
    return response


def get_gateway_stats() -> Dict[str, Any]:
    u"""Return gateway health and routing statistics."""
    try:
        from core.harness.knowledge.domain_router import DomainRouter
        stats = DomainRouter().route_stats()
        return {"gateway": "ok", "routing_stats": stats}
    except Exception as e:
        return {"gateway": "error", "error": str(e)}
