"""Ontology constraint compiler (P1-L3, 六层框架 L3 大脑层).

Compiles T-Box axioms + class field constraints into a natural-language
"hard rules" block that is injected into the system prompt BEFORE LLM
generation — the pre-generation logic lock ("AI 开口前就知道红线在哪").

Sources:
  - AXIOMS (knowledge_ontology): consistency rules with severity (error/info)
  - CLASSES required_fields: "must include field" constraints

Design: pure function, no side effects; injected explicitly by callers that
need business-rule awareness (opt-in via prompt_assembler meta flag), so it
never changes default behaviour or breaks prompt-cache stability.
"""
from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

_HEADER = "[本体业务约束（生成前强制）] 以下规则由本领域本体编译，回答时 MUST 遵守："


def compile_ontology_constraints(domain_id: str = "default",
                                 max_rules: int = 10) -> str:
    """Compile ontology axioms + class constraints into a prompt hard-rules block.

    Returns a ready-to-inject string (empty when the ontology has no rules).
    """
    rules: List[str] = []
    try:
        from core.harness.knowledge.knowledge_ontology import AXIOMS, CLASSES

        # 1. Axiom constraints (business rules with severity)
        for ax in AXIOMS:
            desc = (ax.description or "").strip()
            if not desc:
                continue
            if ax.severity == "error":
                rules.append(f"- MUST：{desc}")
            else:
                rules.append(f"- 应当：{desc}")
            if len(rules) >= max_rules:
                break

        # 2. Class field constraints (required_fields → "must include")
        for cls in CLASSES:
            req = cls.required_fields or []
            if not req:
                continue
            fields = ", ".join(req)
            rules.append(f"- 涉及 {cls.label} 时必须包含字段：{fields}")
            if len(rules) >= max_rules:
                break
    except Exception:
        logger.debug("ontology constraint compile failed", exc_info=True)

    if not rules:
        return ""
    return _HEADER + "\n" + "\n".join(rules)


def compile_axiom_rules(domain_id: str = "default") -> List[str]:
    """Return axiom constraints as a plain list (for JSON-Schema-style use)."""
    rules: List[str] = []
    try:
        from core.harness.knowledge.knowledge_ontology import AXIOMS

        for ax in AXIOMS:
            desc = (ax.description or "").strip()
            if desc:
                rules.append(desc)
    except Exception:
        logger.debug("axiom rule compile failed", exc_info=True)
    return rules
