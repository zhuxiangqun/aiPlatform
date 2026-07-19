u"""
Rule Auditor — 推理规则冲突检测与审计 (v2.7).

Scans inference_rules for: conflicting conclusions, unreachable premises,
missing transitions on classes with states.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("rule_auditor")


def audit_rules(domain_yaml_raw: Dict[str, Any]) -> Dict[str, Any]:
    u"""Run full audit on a domain's inference rules.

    Returns: {"conflicts": [...], "unreachable": [...], "missing_transitions": [...]}
    """
    rules = domain_yaml_raw.get("inference_rules", [])
    if not rules:
        return {"conflicts": [], "unreachable": [], "missing_transitions": [], "total_rules": 0, "has_issues": False, "issue_count": 0}

    result = {
        "conflicts": detect_conflicts(rules),
        "unreachable": detect_unreachable(rules, domain_yaml_raw),
        "missing_transitions": detect_missing_transitions(domain_yaml_raw),
        "total_rules": len(rules),
    }

    total_issues = len(result["conflicts"]) + len(result["unreachable"]) + len(result["missing_transitions"])
    result["has_issues"] = total_issues > 0
    result["issue_count"] = total_issues

    return result


def detect_conflicts(rules: List[Dict]) -> List[Dict[str, Any]]:
    u"""Detect rules with same conclusion relation but contradictory premises."""
    by_conclusion: Dict[str, List[Dict]] = {}
    for rule in rules:
        conc = rule.get("conclusion", {})
        rel = conc.get("relation", "")
        if rel:
            by_conclusion.setdefault(rel, []).append(rule)

    conflicts = []
    for rel, group in by_conclusion.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                r1 = group[i]
                r2 = group[j]
                if _premises_contradict(r1.get("premises", []), r2.get("premises", [])):
                    conflicts.append({
                        "rule_a": r1.get("name", ""),
                        "rule_b": r2.get("name", ""),
                        "conclusion_relation": rel,
                        "reason": "Same conclusion, contradictory premises",
                    })
    return conflicts


def detect_unreachable(rules: List[Dict], domain_raw: Dict) -> List[Dict[str, Any]]:
    u"""Detect rules whose premises reference non-existent relations."""
    obj_props = domain_raw.get("object_properties", [])
    existing_rels = {p.get("name", "") for p in obj_props}

    unreachable = []
    for rule in rules:
        for prem in rule.get("premises", []):
            rel = prem.get("relation", "")
            if rel and rel not in existing_rels:
                unreachable.append({
                    "rule_name": rule.get("name", ""),
                    "missing_relation": rel,
                    "reason": f"Relation '{rel}' not defined in object_properties",
                })
    return unreachable


def detect_missing_transitions(domain_raw: Dict) -> List[Dict[str, Any]]:
    u"""Detect classes with states defined but no transitions."""
    classes = domain_raw.get("classes", {})
    issues = []
    for cls_name, cls_def in classes.items():
        states = cls_def.get("states", {})
        transitions = states.get("transitions", []) or cls_def.get("transitions", [])
        state_enum = states.get("enum", [])
        if len(state_enum) >= 2 and len(transitions) == 0:
            issues.append({
                "class_name": cls_name,
                "state_count": len(state_enum),
                "reason": f"Class has {len(state_enum)} states but 0 transitions",
            })
    return issues


def _premises_contradict(prem_a: List[Dict], prem_b: List[Dict]) -> bool:
    u"""Check if two premise sets are contradictory (simplified: same relation, opposite direction)."""
    rels_a = {(p.get("relation", ""), p.get("direction", "")) for p in prem_a}
    rels_b = {(p.get("relation", ""), p.get("direction", "")) for p in prem_b}
    for rel, direction in rels_a:
        opposite = "incoming" if direction == "outgoing" else "outgoing"
        if (rel, opposite) in rels_b:
            return True
    return False
