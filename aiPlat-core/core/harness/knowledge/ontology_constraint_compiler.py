"""Ontology constraint compiler (P1-L3, 六层框架 L3 大脑层).

Compiles T-Box axioms + class field constraints into a natural-language
"hard rules" block that is injected into the system prompt BEFORE LLM
generation — the pre-generation logic lock ("AI 开口前就知道红线在哪").

Sources (ONTOLOGY_RUNTIME_AUTHORITY §2):
  - Prefer domain YAML axioms/required_fields when domain_id is a loaded domain
  - Fallback: wiki-global AXIOMS/CLASSES (knowledge-base track only)

Design: pure function, no side effects; injected explicitly by callers that
need business-rule awareness (opt-in via prompt_assembler meta flag), so it
never changes default behaviour or breaks prompt-cache stability.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_HEADER = "[本体业务约束（生成前强制）] 以下规则由本领域本体编译，回答时 MUST 遵守："


def _load_domain_or_none(domain_id: str):
    if not domain_id or domain_id in ("default", "ai-knowledge"):
        # default/ai-knowledge may still have YAML; try load, else None
        pass
    try:
        from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
        import os
        from pathlib import Path
        home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
        path = home / "ontologies" / f"{domain_id}.yaml"
        if path.is_file():
            return load_ontology_from_yaml(str(path))
    except Exception:
        logger.debug("domain ontology load failed for %s", domain_id, exc_info=True)
    return None


def _rules_from_domain(domain, max_rules: int) -> List[str]:
    rules: List[str] = []
    for ax in domain.axioms or []:
        desc = (ax.description or "").strip()
        if not desc:
            continue
        if ax.severity == "error":
            rules.append(f"- MUST：{desc}")
        else:
            rules.append(f"- 应当：{desc}")
        if len(rules) >= max_rules:
            return rules
    for cls in domain.classes or []:
        req = cls.required_fields or []
        if not req:
            continue
        fields = ", ".join(req)
        rules.append(f"- 涉及 {cls.label} 时必须包含字段：{fields}")
        if len(rules) >= max_rules:
            break
    return rules


def _rules_from_wiki_global(max_rules: int) -> List[str]:
    rules: List[str] = []
    from core.harness.knowledge.knowledge_ontology import AXIOMS, CLASSES
    for ax in AXIOMS:
        desc = (ax.description or "").strip()
        if not desc:
            continue
        if ax.severity == "error":
            rules.append(f"- MUST：{desc}")
        else:
            rules.append(f"- 应当：{desc}")
        if len(rules) >= max_rules:
            return rules
    for cls in CLASSES:
        req = cls.required_fields or []
        if not req:
            continue
        fields = ", ".join(req)
        rules.append(f"- 涉及 {cls.label} 时必须包含字段：{fields}")
        if len(rules) >= max_rules:
            break
    return rules


def compile_ontology_constraints(domain_id: str = "default",
                                 max_rules: int = 10) -> str:
    """Compile ontology axioms + class constraints into a prompt hard-rules block.

    Business domains: compile from domain YAML (authority track).
    Fallback: wiki-global AXIOMS when domain has no file/axioms.
    """
    rules: List[str] = []
    try:
        domain = _load_domain_or_none(domain_id)
        if domain is not None and (domain.axioms or domain.classes):
            rules = _rules_from_domain(domain, max_rules)
        if not rules:
            # Knowledge-base track fallback (explicit for default/wiki contexts)
            _ = compile_axiom_rules(domain_id)
            rules = _rules_from_wiki_global(max_rules)
    except Exception:
        logger.debug("ontology constraint compile failed", exc_info=True)

    if not rules:
        return ""
    return _HEADER + "\n" + "\n".join(rules)


def compile_axiom_rules(domain_id: str = "default") -> List[str]:
    """Return axiom constraints as a plain list (for JSON-Schema-style use)."""
    rules: List[str] = []
    try:
        domain = _load_domain_or_none(domain_id)
        if domain is not None and domain.axioms:
            for ax in domain.axioms:
                desc = (ax.description or "").strip()
                if desc:
                    rules.append(desc)
            return rules
        from core.harness.knowledge.knowledge_ontology import AXIOMS
        for ax in AXIOMS:
            desc = (ax.description or "").strip()
            if desc:
                rules.append(desc)
    except Exception:
        logger.debug("axiom rule compile failed", exc_info=True)
    return rules
