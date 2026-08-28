"""

import logging
Kernel syscalls (Phase 2).



Syscalls are the only permitted execution entry points for:

- LLM calls

- Tool calls

- Skill calls



NOTE: Keep imports lazy to reduce circular dependencies with execution/skills/tools.

"""



from __future__ import annotations



import importlib

from typing import TYPE_CHECKING, Any



__all__ = [

    "sys_llm_generate", "sys_tool_call", "sys_skill_call",

    "sys_agent_call", "sys_workflow_call",

    "sys_kb_retrieve", "sys_wiki_retrieve", "sys_wiki_context",

    "sys_knowledge_retrieve",

    "sys_routed_retrieve",

    "sys_ontology_context",

    "sys_skill_corpus_search", "sys_skill_corpus_inspect", "sys_skill_corpus_select",

    "sys_drawio_generate",

    "sys_code_intel_context", "sys_code_intel_blast",

    "sys_code_intel_callers", "sys_code_intel_callees",

    "sys_code_intel_affected", "sys_code_intel_search",

    "sys_code_intel_subclasses",

    "sys_file_read", "sys_file_write", "sys_file_edit",

    "sys_glob", "sys_code_search",

    "sys_graph_query",
    "sys_graph_neighbors",      # v3.1: entity neighbor traversal

    "sys_ontology_reason",       # v2.7: Ontology Agent 5-step reasoning

]



_LAZY_MODULES = {

    "llm": ["sys_llm_generate"],

    "tool": ["sys_tool_call"],

    "skill": ["sys_skill_call"],

    "agent": ["sys_agent_call"],

    "workflow": ["sys_workflow_call"],

    "retrieval": ["sys_kb_retrieve", "sys_wiki_retrieve", "sys_knowledge_retrieve",
                  "sys_routed_retrieve"],

    "wiki_context": ["sys_wiki_context"],

    "ontology": ["sys_ontology_context"],

    "skill_corpus": ["sys_skill_corpus_search", "sys_skill_corpus_inspect", "sys_skill_corpus_select"],

    "drawio_gen": ["sys_drawio_generate"],

    "code_intel_syscall": [

        "sys_code_intel_context", "sys_code_intel_blast",

        "sys_code_intel_callers", "sys_code_intel_callees",

        "sys_code_intel_affected", "sys_code_intel_search",

        "sys_code_intel_subclasses",

        "sys_code_intel_affected", "sys_code_intel_search",

    ],

    "file": ["sys_file_read", "sys_file_write", "sys_file_edit"],

    "code": ["sys_glob", "sys_code_search"],

    "graph": ["sys_graph_query", "sys_graph_neighbors"],

    "ontology_reason": ["sys_ontology_reason"],

}





def __getattr__(name: str) -> Any:

    if name not in __all__:

        raise AttributeError(name)

    for mod_name, names in _LAZY_MODULES.items():

        if name in names:

            m = importlib.import_module(f"{__name__}.{mod_name}")

            fn = getattr(m, name)

            if callable(fn):

                return _wrap_with_usage_tracking(name, fn)

            return fn

    raise AttributeError(name)





def _wrap_with_usage_tracking(name: str, fn):

    u"""Wrap syscall functions with usage recording (non-intrusive, fail-safe)."""

    import functools

    import asyncio



    @functools.wraps(fn)

    async def wrapper(*args, **kwargs):

        t0 = __import__('time').time()

        result = await fn(*args, **kwargs)

        latency = (__import__('time').time() - t0) * 1000

        try:

            from core.harness.observability.usage_tracker import record

            event_type = name

            if name == 'sys_llm_generate':

                event_type = 'llm_generate'

            elif name == 'sys_tool_call':

                event_type = 'tool_call'

            elif name == 'sys_skill_call':

                event_type = 'skill_call'

            elif name == 'sys_knowledge_retrieve':

                event_type = 'knowledge_retrieve'

            record(event_type, latency_ms=latency)

        except Exception:

            logging.getLogger(__name__).debug('wrapper failed', exc_info=True)
        return result



    @functools.wraps(fn)

    def sync_wrapper(*args, **kwargs):

        t0 = __import__('time').time()

        result = fn(*args, **kwargs)

        latency = (__import__('time').time() - t0) * 1000

        try:

            from core.harness.observability.usage_tracker import record

            record(name, latency_ms=latency)

        except Exception:

            logging.getLogger(__name__).debug('sync_wrapper failed', exc_info=True)
        return result



    if asyncio.iscoroutinefunction(fn):

        return wrapper

    return sync_wrapper





def __dir__() -> list[str]:

    return sorted(set(globals().keys()) | set(__all__))





if TYPE_CHECKING:

    from .llm import sys_llm_generate

    from .skill import sys_skill_call

    from .tool import sys_tool_call

    from .moa_executor import execute as sys_moa_execute

