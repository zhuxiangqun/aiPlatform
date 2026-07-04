"""SemanticGate — post-generation semantic compliance validation.

Phase 11.2: validates Agent output conclusions against YAML ontology definitions.
Checks that entities, values, and relations mentioned in the output exist within
the defined semantic space of the given ontology domain.

Orthogonal to PolicyGate (execution permission) and ApprovalGate (danger threshold).
SemanticGate checks "is this conclusion semantically valid?" not "is this operation authorized?"

Enabled by: AIPLAT_SEMANTIC_GATE_ENABLED=true (default)
Mode:      AIPLAT_SEMANTIC_GATE_MODE=warn (default) | audit | block
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.semantic_gate")


# ═══════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class Violation:
    type: str       # "entity_not_found" | "value_out_of_range" | "relation_undefined"
    detail: str     # human-readable description
    severity: str   # "low" | "medium" | "high"
    suggestion: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "type": self.type, "detail": self.detail,
            "severity": self.severity, "suggestion": self.suggestion,
        }


@dataclass
class SemanticGateResult:
    valid: bool
    violations: List[Violation] = field(default_factory=list)
    status: str = "pass"  # "pass" | "warn" | "reject"
    checked_at: str = ""


# ═══════════════════════════════════════════════════════════════
# Paths to extract entities from decision JSON
# ═══════════════════════════════════════════════════════════════

_EXTRACT_ENTITY_PATHS = [
    "entity",                         # RunContext entity
    "impact.affected_entities",       # affected_entities list
    "recommended_actions.target",     # action targets
]

_EXTRACT_VALUE_SPECS = {
    "confidence": {"low": 0.0, "high": 1.0, "entity_class": None},
}

# Severity thresholds
_MIN_ENTITY_COUNT_FOR_WARN = 1
_MIN_ENTITY_COUNT_FOR_REJECT = 3


# ═══════════════════════════════════════════════════════════════
# SemanticGate
# ═══════════════════════════════════════════════════════════════

class SemanticGate:
    """Post-generation semantic compliance validator.

    Mode behavior:
      - warn:  runs full validation, marks violations in output but allows through
      - audit: runs full validation, logs violations but does NOT change output status
      - block: runs full validation, reject-status modifies AgentResult metadata
    """

    def __init__(self, mode: str = "warn"):
        self.mode = mode  # "warn" | "audit" | "block"

    def verify(self, output: dict, *, domain_id: str = "default") -> SemanticGateResult:
        """Run all three validation layers against the given domain."""
        import time as _time
        violations: List[Violation] = []

        # Layer 1: entity semantic verification
        try:
            violations.extend(self._verify_entities(output, domain_id))
        except Exception as e:
            logger.debug("Entity verification failed: %s", e)

        # Layer 2: value range verification
        try:
            violations.extend(self._verify_values(output, domain_id))
        except Exception as e:
            logger.debug("Value verification failed: %s", e)

        # Layer 3: relation compliance verification
        try:
            violations.extend(self._verify_relations(output, domain_id))
        except Exception as e:
            logger.debug("Relation verification failed: %s", e)

        status = self._compute_status(violations)
        valid = status == "pass"

        # audit mode: run validation but mark all as pass
        if self.mode == "audit":
            logger.info("SemanticGate audit: %d violations (status forced to pass)", len(violations))
            status = "pass"
            valid = True

        return SemanticGateResult(
            valid=valid,
            violations=violations,
            status=status,
            checked_at=str(int(_time.time())),
        )

    # ═══════════════════════════════════════════════════════════
    # Layer 1: Entity semantic verification
    # ═══════════════════════════════════════════════════════════

    def _verify_entities(self, output: dict, domain_id: str) -> List[Violation]:
        """Check that all named entities exist in GraphIndex."""
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            graph = GraphIndex.load(domain_id)
        except Exception:
            return []  # graph not available → skip

        violations: List[Violation] = []
        for path in _EXTRACT_ENTITY_PATHS:
            values = self._resolve_path(output, path)
            if not isinstance(values, list):
                values = [values] if values else []
            for val in values:
                name = str(val).strip() if val else ""
                if not name or len(name) < 2:
                    continue
                if not graph.find_by_name(name):
                    violations.append(Violation(
                        type="entity_not_found",
                        detail=f"实体 '{name}' 在本体域 '{domain_id}' 的 GraphIndex 中未定义",
                        severity="medium",
                        suggestion=f"检查 '{name}' 是否在本体 YAML classes[] 中有注册，是否为拼写错误",
                    ))
        return violations

    # ═══════════════════════════════════════════════════════════
    # Layer 2: Value range verification
    # ═══════════════════════════════════════════════════════════

    def _verify_values(self, output: dict, domain_id: str) -> List[Violation]:
        """Check that numeric values are within defined ranges."""
        violations: List[Violation] = []
        for path, spec in _EXTRACT_VALUE_SPECS.items():
            value = self._resolve_path(output, path, single=True)
            if value is None:
                continue
            try:
                v = float(value)
            except (ValueError, TypeError):
                continue
            low, high = spec["low"], spec["high"]
            if not (low <= v <= high):
                violations.append(Violation(
                    type="value_out_of_range",
                    detail=f"字段 '{path}' 的值 {v} 超出范围 [{low}, {high}]",
                    severity="medium",
                    suggestion=f"将 {path} 调整至 [{low}, {high}] 范围内",
                ))
        return violations

    # ═══════════════════════════════════════════════════════════
    # Layer 3: Relation compliance verification
    # ═══════════════════════════════════════════════════════════

    def _verify_relations(self, output: dict, domain_id: str) -> List[Violation]:
        """Check that asserted relations are defined in ontology."""
        violations: List[Violation] = []

        # Only strict-check in block mode — relation names in actions
        # are business operation names, not ontology relation names
        if self.mode != "block":
            return violations

        actions = output.get("recommended_actions", [])
        if not isinstance(actions, list):
            return violations

        try:
            from core.harness.knowledge.knowledge_ontology import OBJECT_PROPERTIES
            known_relations = {p.name.lower() for p in OBJECT_PROPERTIES}
        except Exception:
            return violations

        for action in actions:
            action_name = str(action.get("action", "")).strip().lower()
            if not action_name:
                continue
            # Check if any known relation name is in the action name
            if not any(rel in action_name for rel in known_relations):
                violations.append(Violation(
                    type="relation_undefined",
                    detail=f"操作 '{action.get('action', '')}' 在本体 object_properties 中无对应关系",
                    severity="low",
                    suggestion=f"确认操作名称是否在 YAML 域本体的 object_properties[] 中有定义",
                ))

        return violations

    # ═══════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════

    def _resolve_path(
        self, data: Any, path: str, *, single: bool = False
    ) -> Optional[Any]:
        """Resolve a dot-separated path in a nested dict/list.

        Examples:
          "entity" → data.get("entity")
          "impact.affected_entities" → data["impact"]["affected_entities"]
          "recommended_actions.target" → [a["target"] for a in data["recommended_actions"]]

        When single=True, returns the first found value rather than a list.
        """
        parts = path.split(".")
        current = data
        for i, part in enumerate(parts):
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # If this is the last part, extract field from each item
                if i == len(parts) - 1:
                    results = []
                    for item in current:
                        if isinstance(item, dict) and part in item:
                            results.append(item[part])
                    return results[0] if single and results else results if results else None
                return None
            else:
                return None
        if isinstance(current, list) and not single:
            return current
        return current

    def _compute_status(self, violations: List[Violation]) -> str:
        """Determine gate status from violation count and severity."""
        if not violations:
            return "pass"
        high_count = sum(1 for v in violations if v.severity == "high")
        total = len(violations)
        if high_count > 0 or total >= _MIN_ENTITY_COUNT_FOR_REJECT:
            return "reject"
        if total >= _MIN_ENTITY_COUNT_FOR_WARN:
            return "warn"
        return "pass"
