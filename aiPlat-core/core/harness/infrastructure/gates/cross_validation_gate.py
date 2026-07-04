"""CrossValidationGate — cross-domain semantic validation (Phase 11.3, framework stub).

Implements equipment + process + quality three-layer cross-validation as described
in Knora 4.0's LED production line scenario. Validates that decisions span multiple
ontology domains correctly — e.g., "equipment temperature suggestion must not exceed
process soldering quality threshold."

ACTIVATION CONDITION:
  This gate activates when >=50 cross-domain object_properties exist in the ontology.
  Current count can be checked with:
    grep -c 'domain.*range' ~/.aiplat/ontologies/*.yaml

When the threshold is met, implement these layers:

  Layer 1 — Equipment ↔ Process:
    For each entity in the decision, check if the suggested action (e.g.,
    "increase temperature") conflicts with the upstream/downstream process
    constraints defined in object_properties.

  Layer 2 — Process ↔ Quality:
    Verify that process parameter changes don't violate quality thresholds
    defined in the quality_parameters ontology class.

  Layer 3 — Equipment ↔ Quality:
    Direct cross-check: does the equipment's current state (from RunContext)
    imply quality degradation according to the ontology's inference_rules?

Example violation:
  "回流炉 temperature 建议值 235℃ 超出焊接质量阈值 230℃"
  → cross_violation: equipment.temperature vs process.soldering_quality.threshold
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.cross_validation_gate")


@dataclass
class CrossViolation:
    layer: str       # "equipment_process" | "process_quality" | "equipment_quality"
    detail: str
    severity: str    # "low" | "medium" | "high"


@dataclass
class CrossValidationResult:
    valid: bool
    cross_violations: List[CrossViolation] = field(default_factory=list)
    layers_checked: List[str] = field(default_factory=list)
    reason: str = ""


class CrossValidationGate:
    """Equipment + Process + Quality layer cross-validation.

    Currently a framework stub — activates when cross-domain object_properties
    count reaches the activation threshold.
    """

    _ACTIVATION_THRESHOLD = 50

    @classmethod
    def is_ready(cls) -> bool:
        """Check if enough cross-domain connections exist to activate."""
        try:
            import os
            import yaml
            onto_dir = os.path.expanduser("~/.aiplat/ontologies")
            if not os.path.isdir(onto_dir):
                return False

            cross_count = 0
            for fname in os.listdir(onto_dir):
                if not fname.endswith(".yaml"):
                    continue
                with open(os.path.join(onto_dir, fname)) as f:
                    data = yaml.safe_load(f) or {}
                props = data.get("object_properties", [])
                for p in props:
                    if isinstance(p, dict) and p.get("domain") and p.get("range"):
                        cross_count += 1

            logger.debug(
                "CrossValidationGate readiness: %d/%d cross-domain properties",
                cross_count, cls._ACTIVATION_THRESHOLD,
            )
            return cross_count >= cls._ACTIVATION_THRESHOLD
        except Exception as e:
            logger.debug("CrossValidationGate readiness check failed: %s", e)
            return False

    def verify(self, output: dict, *, domain_id: str = "default") -> CrossValidationResult:
        """Run cross-domain validation. Raises NotImplementedError if not ready."""
        if not self.is_ready():
            raise NotImplementedError(
                "CrossValidationGate requires >=50 cross-domain object_properties "
                "in the ontology YAML files. Check with:\n"
                "  grep -c 'domain.*range' ~/.aiplat/ontologies/*.yaml\n"
                "See docs/decisions/adr-011-cross-validation.md for activation criteria."
            )

        result = CrossValidationResult(
            valid=True,
            layers_checked=[],
            reason="CrossValidationGate activated but not yet implemented. "
                   "Implement _verify_equipment_process(), _verify_process_quality(), "
                   "_verify_equipment_quality() methods.",
        )
        return result
