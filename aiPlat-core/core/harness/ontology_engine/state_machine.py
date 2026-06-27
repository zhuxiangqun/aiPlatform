"""
State Machine Engine — YAML-driven deterministic state transition evaluator.

Architecture:
  States and transitions are defined in YAML (ai-knowledge.yaml, etc.),
  loaded into OntologyClass.states / .transitions / .side_effects.
  This engine is pure-rule: zero LLM, zero async, deterministic.

Usage:
  sm = StateMachine(domain)
  result = sm.evaluate_instance(instance, context)
  # → StateTransitionResult | None
"""

from __future__ import annotations
import logging

import re as _re
import time as _time
from typing import Any, Dict, List, Optional


class EvalContext:
    """Evaluation context containing all instances and their relations."""

    def __init__(self, instances: List[Dict[str, Any]]):
        self._instances = instances
        # Build class index: class_label → list of instances
        self._class_index: Dict[str, List[Dict[str, Any]]] = {}
        # Build chunk index: chunk_id → list of instances (co-occurrence)
        self._chunk_index: Dict[str, List[Dict[str, Any]]] = {}
        for inst in instances:
            cls = str(inst.get("class_name", ""))
            self._class_index.setdefault(cls, []).append(inst)
            cid = str(inst.get("chunk_id", ""))
            if cid:
                self._chunk_index.setdefault(cid, []).append(inst)

    def count_by_class(self, class_label: str) -> int:
        """Count all instances of a given class in the context."""
        return len(self._class_index.get(class_label, []))

    def count_co_occurring(self, class_label: str, focal_instance: Dict[str, Any]) -> int:
        """Count instances of class_label that co-occur with the focal instance.

        Two instances co-occur if they share at least one chunk_id.
        If no chunk-level co-occurrence found, falls back to class-level
        counting (all instances in document), which is the correct behavior
        when each chunk produces exactly one instance.
        """
        focal_cids = self._chunk_ids_of(focal_instance)
        if not focal_cids or not self._chunk_index:
            return self.count_by_class(class_label)
        co_occurring = set()
        for cid in focal_cids:
            for inst in self._chunk_index.get(cid, []):
                if inst is not focal_instance and inst.get("class_name") == class_label:
                    key = inst.get("entity_text") or inst.get("properties", {}).get("name", "")
                    if key:
                        co_occurring.add(key)
        if co_occurring:
            return len(co_occurring)
        # Fallback: document-level count, excluding focal instance
        raw_count = self.count_by_class(class_label)
        focal_cls = str(focal_instance.get("class_name", ""))
        if focal_cls == class_label and raw_count > 0:
            raw_count -= 1  # exclude self
        return max(0, raw_count)

    def has_instance_of(self, class_label: str) -> bool:
        return self.count_by_class(class_label) > 0

    def all_instances(self) -> List[Dict[str, Any]]:
        return self._instances

    def _chunk_ids_of(self, instance: Dict[str, Any]) -> List[str]:
        cid = str(instance.get("chunk_id", ""))
        return [cid] if cid else []


class StateTransitionResult:
    """Result of a successful state transition evaluation."""

    def __init__(
        self,
        instance_title: str,
        class_name: str,
        from_state: str,
        to_state: str,
        trigger_type: str,
        transition_desc: str = "",
        side_effects: Optional[List[Dict[str, Any]]] = None,
    ):
        self.instance_title = instance_title
        self.class_name = class_name
        self.from_state = from_state
        self.to_state = to_state
        self.trigger_type = trigger_type
        self.transition_desc = transition_desc
        self.side_effects = side_effects or []

    def to_dict(self) -> dict:
        return {
            "instance_title": self.instance_title,
            "class_name": self.class_name,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger_type": self.trigger_type,
            "transition_desc": self.transition_desc,
            "side_effects": self.side_effects,
        }


class StateMachine:
    """Pure-rule state machine evaluator, driven entirely by YAML config."""

    def __init__(self, domain):
        """Initialize from an OntologyDomain loaded from YAML."""
        self._domain = domain
        self._cls_by_label: Dict[str, Any] = {}
        for cls in domain.classes:
            self._cls_by_label[cls.label] = cls

    def evaluate_instance(
        self,
        instance: Dict[str, Any],
        context: EvalContext,
    ) -> Optional[StateTransitionResult]:
        """Evaluate transitions, iterating to stability (chain all that fire)."""
        chain = self.evaluate_chain(instance, context)
        return chain[-1] if chain else None

    def evaluate_chain(
        self,
        instance: Dict[str, Any],
        context: EvalContext,
    ) -> List[StateTransitionResult]:
        """Return the full chain of state transitions, or empty list."""
        class_name = str(instance.get("class_name", ""))
        cls = self._cls_by_label.get(class_name)
        if cls is None:
            return []

        states_cfg = getattr(cls, "states", None) or {}
        transitions_cfg = getattr(cls, "transitions", None) or []
        side_effects_cfg = getattr(cls, "side_effects", None) or []

        if not states_cfg or not transitions_cfg:
            return []

        chain: List[StateTransitionResult] = []
        current = self._get_current_state(instance, states_cfg)
        max_iter = len(transitions_cfg) + 1

        for _ in range(max_iter):
            fired = None
            for trans in transitions_cfg:
                from_states = trans.get("from", [])
                if isinstance(from_states, str):
                    from_states = [from_states]
                if current not in from_states:
                    continue

                trigger = trans.get("trigger", {})
                trigger_type = str(trigger.get("type", ""))

                if self._eval_trigger(trigger_type, trigger, instance, context):
                    to_state = trans.get("to", "")
                    if not to_state or to_state == current:
                        continue

                    triggered_effects = self._match_side_effects(side_effects_cfg, to_state)

                    fired = StateTransitionResult(
                        instance_title=(
                            instance.get("properties", {}).get("title")
                            or instance.get("properties", {}).get("name")
                            or instance.get("entity_text", "unknown")
                        ),
                        class_name=class_name,
                        from_state=current,
                        to_state=to_state,
                        trigger_type=trigger_type,
                        transition_desc=str(trans.get("description", "")),
                        side_effects=triggered_effects,
                    )
                    current = to_state
                    chain.append(fired)
                    break

            if not fired:
                break

        return chain

    # ── Trigger Evaluators ───────────────────────────────────────────

    def _eval_trigger(
        self,
        trigger_type: str,
        trigger: Dict[str, Any],
        instance: Dict[str, Any],
        context: EvalContext,
    ) -> bool:
        if trigger_type == "relation_count":
            return self._eval_relation_count(trigger, instance, context)
        elif trigger_type == "property_condition":
            return self._eval_property_condition(trigger, instance)
        elif trigger_type == "relation_exists":
            return self._eval_relation_exists(trigger, context)
        return False

    def _eval_relation_count(
        self,
        trigger: Dict[str, Any],
        instance: Dict[str, Any],
        context: EvalContext,
    ) -> bool:
        """Count instances of the target class that co-occur with this instance."""
        relation_name = str(trigger.get("relation", ""))
        threshold = int(trigger.get("threshold", 1))
        operator = str(trigger.get("operator", ">="))

        target_class = self._relation_to_target_class(relation_name)
        if not target_class:
            return False

        count = context.count_co_occurring(target_class, instance)
        if operator == ">=":
            return count >= threshold
        elif operator == ">":
            return count > threshold
        elif operator == "<":
            return count < threshold
        elif operator == "<=":
            return count <= threshold
        elif operator == "==":
            return count == threshold
        return False

    def _eval_property_condition(
        self,
        trigger: Dict[str, Any],
        instance: Dict[str, Any],
    ) -> bool:
        """Check an instance's property value against a condition.

        Supported:
          "exists"             — non-None, non-empty
          "true"/"false"       — boolean value
          ">= N", "> N", ...   — numeric threshold
          "in:a,b,c"           — string inclusion
        """
        field = str(trigger.get("field", ""))
        condition = str(trigger.get("condition", ""))

        props = instance.get("properties", {}) or {}
        value = props.get(field)

        if condition == "exists":
            return value is not None and (not isinstance(value, str) or bool(value.strip()))

        if condition.lower() in ("true", "false"):
            return bool(value) == (condition.lower() == "true")

        m = _re.match(r"^\s*(>=|<=|>|<|==)\s*(\d+(?:\.\d+)?)\s*$", condition)
        if m:
            op, target = m.group(1), float(m.group(2))
            try:
                v = float(value) if not isinstance(value, (int, float)) else float(value)
                if op == ">=":
                    return v >= target
                elif op == ">":
                    return v > target
                elif op == "<":
                    return v < target
                elif op == "<=":
                    return v <= target
                elif op == "==":
                    return v == target
            except (TypeError, ValueError):
                return False

        m = _re.match(r"^\s*in\s*:\s*(.+)$", condition)
        if m:
            allowed = [x.strip() for x in m.group(1).split(",")]
            return str(value) in allowed

        return False

    def _eval_relation_exists(
        self,
        trigger: Dict[str, Any],
        context: EvalContext,
    ) -> bool:
        """Check if at least one OTHER instance of the target class exists."""
        relation_name = str(trigger.get("relation", ""))
        target_class = self._relation_to_target_class(relation_name)
        if not target_class:
            return False
        return context.count_by_class(target_class) >= 2

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_current_state(self, instance: Dict[str, Any], states_cfg: Dict[str, Any]) -> str:
        """Determine the current state of an instance."""
        props = instance.get("properties", {}) or {}
        state_enum = {s["name"] for s in (states_cfg.get("enum") or [])}
        state_val = props.get("state")
        if state_val and str(state_val) in state_enum:
            return str(state_val)
        maturity_val = props.get("maturity")
        if maturity_val and str(maturity_val) in state_enum:
            return str(maturity_val)
        return str(states_cfg.get("default", "unknown"))

    def _relation_to_target_class(self, relation_name: str) -> str:
        """Map a relation name (name, label, or inverse_label) to the target class label."""
        for prop in self._domain.object_properties:
            label = getattr(prop, "label", "")
            inv_label = getattr(prop, "inverse_label", "")
            name = getattr(prop, "uri", "").rsplit("#", 1)[-1].rsplit("/", 1)[-1]
            matched = (name == relation_name or label == relation_name or inv_label == relation_name)
            if not matched:
                continue
            if label == relation_name or name == relation_name:
                ranges = getattr(prop, "range", [])
                for r_uri in ranges:
                    for cls in self._domain.classes:
                        if cls.uri == r_uri:
                            return cls.label
            if inv_label == relation_name:
                domains = getattr(prop, "domain", [])
                for d_uri in domains:
                    for cls in self._domain.classes:
                        if cls.uri == d_uri:
                            return cls.label
        return ""

    def _match_side_effects(
        self,
        side_effects_cfg: List[Dict[str, Any]],
        to_state: str,
    ) -> List[Dict[str, Any]]:
        """Find side effects that match the target state."""
        matched = []
        for effect in side_effects_cfg:
            when = str(effect.get("when", ""))
            try:
                if self._simple_eval(when, {"to": to_state}):
                    matched.append(effect)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return matched

    @staticmethod
    def _simple_eval(expr: str, ctx: Dict[str, Any]) -> bool:
        """Minimal expression evaluator for 'to == value' conditions."""
        expr = expr.strip()
        m = _re.match(r"""^to\s*==\s*["'](.+)["']$""", expr)
        if m:
            return ctx.get("to", "") == m.group(1)
        m = _re.match(r"^to\s*==\s*(\S+)$", expr)
        if m:
            return ctx.get("to", "") == m.group(1)
        return False


def compute_indicators(instances: List[Dict[str, Any]], context: EvalContext) -> None:
    """Compute derived property indicators for each instance from co-occurrence data.

    Injects computed fields into instance["properties"]:
      _cooc_<ClassName>   — co-occurring instance count per class
      enterprise_adoptions — count of co-occurring instances with enterprise keywords
      has_competing        — bool, another instance of same class co-occurs
    """
    enterprise_keywords = ("enterprise", "企业", "production", "生产", "product", "工业")

    for inst in instances:
        props = inst.setdefault("properties", {})
        cls_name = str(inst.get("class_name", ""))

        for target_cls in context._class_index:
            count = context.count_co_occurring(target_cls, inst)
            if count > 0:
                props[f"_cooc_{target_cls}"] = count
                props[f"cooc_{target_cls}"] = count  # Public alias

        enterprise_count = 0
        for cid in context._chunk_ids_of(inst):
            for other in context._chunk_index.get(cid, []):
                if other is not inst:
                    name = str(other.get("properties", {}).get("name", "") or "")
                    desc = str(other.get("properties", {}).get("description", "") or "")
                    dep = str(other.get("properties", {}).get("deployment_status", "") or "")
                    combined = (name + desc + dep).lower()
                    if any(kw in combined for kw in enterprise_keywords):
                        enterprise_count += 1
        if enterprise_count > 0:
            props["enterprise_adoptions"] = enterprise_count

        same_class_count = context.count_co_occurring(cls_name, inst)
        if same_class_count >= 1:
            props["has_competing"] = True
