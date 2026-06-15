"""
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
    "sys_ontology_context",
    "sys_skill_corpus_search", "sys_skill_corpus_inspect", "sys_skill_corpus_select",
    "sys_code_intel_context", "sys_code_intel_blast",
    "sys_code_intel_callers", "sys_code_intel_callees",
    "sys_code_intel_affected", "sys_code_intel_search",
    "sys_code_intel_subclasses",
    "sys_file_read", "sys_file_write", "sys_file_edit",
    "sys_glob", "sys_code_search",
]

_LAZY_MODULES = {
    "llm": ["sys_llm_generate"],
    "tool": ["sys_tool_call"],
    "skill": ["sys_skill_call"],
    "agent": ["sys_agent_call"],
    "workflow": ["sys_workflow_call"],
    "retrieval": ["sys_kb_retrieve", "sys_wiki_retrieve", "sys_knowledge_retrieve"],
    "wiki_context": ["sys_wiki_context"],
    "ontology_context": ["sys_ontology_context"],
    "skill_corpus": ["sys_skill_corpus_search", "sys_skill_corpus_inspect", "sys_skill_corpus_select"],
    "code_intel_syscall": [
        "sys_code_intel_context", "sys_code_intel_blast",
        "sys_code_intel_callers", "sys_code_intel_callees",
        "sys_code_intel_affected", "sys_code_intel_search",
        "sys_code_intel_subclasses",
        "sys_code_intel_affected", "sys_code_intel_search",
    ],
    "file": ["sys_file_read", "sys_file_write", "sys_file_edit"],
    "code": ["sys_glob", "sys_code_search"],
}


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    for mod_name, names in _LAZY_MODULES.items():
        if name in names:
            m = importlib.import_module(f"{__name__}.{mod_name}")
            return getattr(m, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))


if TYPE_CHECKING:
    from .llm import sys_llm_generate
    from .skill import sys_skill_call
    from .tool import sys_tool_call
