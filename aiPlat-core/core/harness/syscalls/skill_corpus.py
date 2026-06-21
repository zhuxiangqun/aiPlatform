"""
sys_skill_corpus — Agentic Skill Router syscalls.

Primitives: search → inspect → select
Enables Agent to find disabled/low-frequency skills in cold storage.

Phase ASR (Agentic Skill Routing).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def sys_skill_corpus_search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    u"""Search skill metadata corpus (including disabled skills).

    Returns candidates with ref, name, description snippet, score, truncated flag.
    """
    from core.harness.integration import get_skill_registry
    reg = get_skill_registry()
    return reg.search_corpus(query, limit=limit)


def sys_skill_corpus_inspect(ref: str) -> Optional[Dict[str, Any]]:
    u"""Inspect a candidate skill's full metadata (NOT body).

    Returns name, description, triggers, tags, execution_type, category, skill_chain.
    """
    from core.harness.integration import get_skill_registry
    reg = get_skill_registry()
    return reg.inspect_corpus(ref)


def sys_skill_corpus_select(
    ref: str, query: str, reason: str, confidence: str = "medium"
) -> Dict[str, Any]:
    u"""Select a skill from the corpus. Records audit + returns body.

    Auto-enables the skill if it gets selected 3+ times.
    """
    from core.harness.integration import get_skill_registry
    reg = get_skill_registry()
    return reg.select_corpus(ref, query, reason, confidence)
