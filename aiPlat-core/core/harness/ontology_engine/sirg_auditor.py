"""SIRG auditor (P1-L4b, 六层框架 L4 交规层) — reasoning vs rule-chain consistency.

SIRG (Semantic Internal Reasoning Graph) checks whether the model's actual
reasoning steps covered the ontology's required rule chain for a conclusion:

    rule_chain_for(conclusion)   → required rules (standard axiom path)
    audit_reasoning(actual_ids)  → missing/extra rules + violation report

The "actual reasoning chain" is the observable approximation: rule names the
executor actually fired (from decision_trace / tool-call audit / inference
rule_hits). It does NOT depend on LLM internal representations (logits), so
it works with the existing observability surface.

Design: pure functions over GraphInference rule sets; never mutates state.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class SirgAuditor:
    """Audit actual reasoning against the ontology's required rule chain."""

    def __init__(self, rules: List[Dict[str, Any]]):
        self._rules = rules or []

    @classmethod
    def from_inference(cls, inference: Any) -> "SirgAuditor":
        """Build from a GraphInference instance (its runtime rule set)."""
        try:
            rules = inference.list_rules() if hasattr(inference, "list_rules") else []
        except Exception:
            rules = []
        return cls(rules)

    def rule_chain_for(self, conclusion_relation: str) -> List[str]:
        """Required rule chain: every rule whose conclusion produces the given
        relation (the standard axiom path the reasoning MUST cover)."""
        chain = []
        for rule in self._rules:
            concl = rule.get("conclusion") or {}
            if str(concl.get("relation", "")) == conclusion_relation:
                chain.append(str(rule.get("name", "")))
        return chain

    def audit_reasoning(
        self,
        actual_rule_ids: List[str],
        conclusion_relation: str,
    ) -> Dict[str, Any]:
        """Compare actual fired rules vs the required chain for a conclusion.

        Returns a structured report:
          - required_chain: rule names that must be covered
          - fired:          rules actually fired (deduplicated)
          - missing:        required but not fired → violation ("跳过了 XXX")
          - extra:          fired but not required (informational)
          - consistent:     True when no required rule is missing
          - violation_report: human-readable message
        """
        required = self.rule_chain_for(conclusion_relation)
        fired = list(dict.fromkeys(actual_rule_ids or []))
        missing = [r for r in required if r not in fired]
        extra = [r for r in fired if r not in required]
        consistent = not missing
        if consistent:
            report = f"推理链完整：结论 '{conclusion_relation}' 所需 {len(required)} 条规则均已覆盖。"
        else:
            report = (
                f"推理违规：结论 '{conclusion_relation}' 跳过 "
                f"{len(missing)} 条必要规则（{', '.join(missing)}）。"
            )
        return {
            "conclusion_relation": conclusion_relation,
            "required_chain": required,
            "fired": fired,
            "missing": missing,
            "extra": extra,
            "consistent": consistent,
            "violation_report": report,
        }


def audit_trace_rules(
    inference: Any,
    fired_rule_ids: List[str],
    conclusion_relation: str,
) -> Dict[str, Any]:
    """Convenience: audit against a live GraphInference's rule set."""
    auditor = SirgAuditor.from_inference(inference)
    return auditor.audit_reasoning(fired_rule_ids, conclusion_relation)
