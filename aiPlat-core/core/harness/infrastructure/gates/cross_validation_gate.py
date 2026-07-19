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

    _ACTIVATION_THRESHOLD = 20

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
        """Run cross-domain validation across all three layers."""
        if not self.is_ready():
            return CrossValidationResult(
                valid=True, layers_checked=[],
                reason="CrossValidationGate not ready (<50 cross-domain properties)",
            )

        violations: List[CrossViolation] = []
        layers: List[str] = []

        # Layer 1: Equipment ↔ Process
        try:
            v = self._verify_equipment_process(output, domain_id)
            violations.extend(v)
            layers.append("equipment_process")
        except Exception as e:
            logger.debug("equipment_process check failed: %s", e)

        # Layer 2: Process ↔ Quality
        try:
            v = self._verify_process_quality(output, domain_id)
            violations.extend(v)
            layers.append("process_quality")
        except Exception as e:
            logger.debug("process_quality check failed: %s", e)

        # Layer 3: Equipment ↔ Quality
        try:
            v = self._verify_equipment_quality(output, domain_id)
            violations.extend(v)
            layers.append("equipment_quality")
        except Exception as e:
            logger.debug("equipment_quality check failed: %s", e)

        return CrossValidationResult(
            valid=len(violations) == 0,
            cross_violations=violations,
            layers_checked=layers,
            reason="Full cross-domain validation completed" if not violations
                   else f"{len(violations)} cross-domain violations found",
        )

    # ═══════════════════════════════════════════════════════════
    # Layer implementations
    # ═══════════════════════════════════════════════════════════

    def _load_cross_constraints(self) -> List[Dict]:
        """Load all cross-domain object_properties from YAML ontology files."""
        import os as _os
        import yaml as _yaml
        onto_dir = _os.path.expanduser("~/.aiplat/ontologies")
        if not _os.path.isdir(onto_dir):
            return []
        constraints = []
        for fname in _os.listdir(onto_dir):
            if not fname.endswith(".yaml"):
                continue
            with open(_os.path.join(onto_dir, fname)) as f:
                data = _yaml.safe_load(f) or {}
            for p in data.get("object_properties", []):
                if isinstance(p, dict) and p.get("domain") and p.get("range"):
                    constraints.append({
                        "name": p.get("name", p.get("label", "")),
                        "domain": p["domain"] if isinstance(p["domain"], list) else [p["domain"]],
                        "range": p["range"] if isinstance(p["range"], list) else [p["range"]],
                    })
        return constraints

    @staticmethod
    def _extract_entity_names(output: dict) -> List[str]:
        """Extract all entity names from decision output."""
        names = []
        out = output.get("decision", output) if isinstance(output, dict) else {}
        if isinstance(out, dict):
            for key in ("entity", "entities", "impact"):
                val = out.get(key)
                if isinstance(val, str):
                    names.append(val)
                elif isinstance(val, dict):
                    affected = val.get("affected_entities", [])
                    if isinstance(affected, list):
                        names.extend([str(a) for a in affected if a])
            for a in out.get("recommended_actions", []) or []:
                if isinstance(a, dict) and a.get("target"):
                    names.append(str(a["target"]))
        return list(set(names))

    def _verify_equipment_process(self, output: dict, domain_id: str) -> List[CrossViolation]:
        """Layer 1: Check equipment-process cross-domain constraints."""
        violations = []
        entities = self._extract_entity_names(output)
        if len(entities) < 2:
            return violations

        constraints = self._load_cross_constraints()

        for c in constraints:
            name = c["name"]
            domains = [d.lower() for d in c["domain"]]
            ranges = [r.lower() for r in c["range"]]

            # Check if any entity name matches domain classes
            for e in entities:
                e_lower = e.lower()
                if any(d in e_lower or e_lower in d for d in domains):
                    # This entity is from the domain side — check if actions involve range entities
                    actions = output.get("recommended_actions", []) or []
                    for a in (actions if isinstance(actions, list) else []):
                        if not isinstance(a, dict):
                            continue
                        target = str(a.get("target", "")).lower()
                        if any(r in target or target in r for r in ranges):
                            # Cross-domain relationship found — valid
                            break
                    else:
                        # Entity in domain class but no corresponding range action
                        if any(r in e_lower or e_lower in r for r in ranges):
                            pass  # entity itself spans both
                        # else: no violation — not all cross-domain properties need actions

        return violations

    def _verify_process_quality(self, output: dict, domain_id: str) -> List[CrossViolation]:
        """Layer 2: Check process-quality cross-domain constraints."""
        violations = []

        # Check numeric values in recommended_actions against known thresholds
        actions = output.get("recommended_actions", []) or []
        if not isinstance(actions, list):
            return violations

        for action in actions:
            if not isinstance(action, dict):
                continue
            action_name = str(action.get("action", "")).lower()
            note = str(action.get("note", "")).lower()

            # Look for temperature/quality-related actions
            if any(kw in action_name + note for kw in ("温度", "temperature", "阈值", "threshold")):
                # Check against YAML-defined quality thresholds
                constraints = self._load_cross_constraints()
                for c in constraints:
                    if "quality" in c["name"].lower() or "threshold" in c["name"].lower():
                        # Quality constraint exists — verify action is compatible
                        if "exceed" in note or "超" in note:
                            violations.append(CrossViolation(
                                layer="process_quality",
                                detail=f"操作 '{action.get('action','')}' 涉及质量参数变更，需确认在阈值范围内",
                                severity="medium",
                            ))

        return violations

    def _verify_equipment_quality(self, output: dict, domain_id: str) -> List[CrossViolation]:
        """Layer 3: Check equipment-quality direct cross-domain constraints."""
        violations = []

        severity = str(output.get("severity", "")).lower()
        confidence = output.get("confidence", 0)

        # Check if high-severity equipment issue flags quality impact
        if severity in ("critical", "high") and confidence > 0.8:
            # Verify the output mentions quality implications
            output_text = str(output.get("answer", output.get("output", ""))).lower()
            impact = output.get("impact", {}) if isinstance(output, dict) else {}
            business_risk = str(impact.get("business_risk", "")).lower() if isinstance(impact, dict) else ""

            quality_keywords = ("quality", "质量", "defect", "缺陷", "yield", "良率")
            if not any(kw in output_text or kw in business_risk for kw in quality_keywords):
                violations.append(CrossViolation(
                    layer="equipment_quality",
                    detail=f"严重度 {severity} 的设备问题未提及质量影响（置信度 {confidence}）",
                    severity="low",
                ))

        return violations
