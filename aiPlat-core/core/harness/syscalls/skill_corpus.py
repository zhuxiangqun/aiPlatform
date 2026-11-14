"""
sys_skill_corpus — Agentic Skill Router syscalls.

Primitives: search → inspect → select
Enables Agent to find disabled/low-frequency skills in cold storage.

Phase ASR (Agentic Skill Routing).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def sys_skill_corpus_search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search skill metadata corpus (including disabled skills).

    Args:
        query: 查询。
        limit: 返回条数上限。
    """
    from core.harness.integration import get_skill_registry
    reg = get_skill_registry()
    return reg.search_corpus(query, limit=limit)


def sys_skill_corpus_inspect(ref: str) -> Optional[Dict[str, Any]]:
    """Inspect a candidate skill's full metadata (NOT body).

    Args:
        ref: ref 参数。
    """
    from core.harness.integration import get_skill_registry
    reg = get_skill_registry()
    return reg.inspect_corpus(ref)


def sys_skill_corpus_select(
    ref: str, query: str, reason: str, confidence: str = "medium"
) -> Dict[str, Any]:
    """Select a skill from the corpus. Records audit + returns body.

    Args:
        ref: ref 参数。
        query: 查询。
        reason: reason 参数。
        confidence: confidence 参数。
    """
    from core.harness.integration import get_skill_registry
    reg = get_skill_registry()
    return reg.select_corpus(ref, query, reason, confidence)
