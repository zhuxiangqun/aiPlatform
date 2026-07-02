"""
Success Generalizer — decontextualize concrete successes into reusable rules.

Transforms successful pipeline executions into parameterized, generalizable
patterns following the "情节记忆 ETL" pipeline:
  Construct Episode → Extract Success → Generalize → Store as Reusable Rule

Usage:
    from core.harness.learning.success_generalizer import SuccessGeneralizer, get_success_generalizer

    gen = get_success_generalizer()
    rule = await gen.generalize(task_skill, trajectory_summary="script + stdout")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger("aiplat.success_generalizer")


@dataclass
class GeneralizedRule:
    rule_id: str
    condition: str        # When does this rule apply?
    action: str           # What action to take?
    abstracted_from: str  # Source TaskSkill ID
    confidence: float     # 0.0 - 1.0
    verified_count: int   # How many successful runs support this rule
    domain: str = "default"
    status: str = "tentative"  # tentative | verified | deprecated

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "condition": self.condition,
            "action": self.action,
            "abstracted_from": self.abstracted_from,
            "confidence": round(self.confidence, 3),
            "verified_count": self.verified_count,
            "domain": self.domain,
            "status": self.status,
        }


class SuccessGeneralizer:
    """Extracts generalizable rules from concrete successful executions."""

    def __init__(self, min_confidence: float = 0.7, min_verified: int = 2):
        self._min_confidence = min_confidence
        self._min_verified = min_verified
        self._rules: Dict[str, GeneralizedRule] = {}
        self._param_patterns = [
            re.compile(r"(/[\w/.\-]+)"),
            re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})"),
            re.compile(r"([\w.-]+\.(?:log|txt|json|yaml|yml|xml|csv|conf|cfg|ini|toml|env))"),
            re.compile(r"(?i)(docker|kubernetes|nginx|redis|postgres|mysql|mongo|elasticsearch|kafka)"),
        ]

    async def generalize(
        self, task_skill, trajectory_summary: str = ""
    ) -> Optional[GeneralizedRule]:
        try:
            skill_id = getattr(task_skill, "skill_id", task_skill.get("skill_id", "")) if not isinstance(task_skill, str) else task_skill
            name = getattr(task_skill, "name", task_skill.get("name", "")) if not isinstance(task_skill, str) else task_skill
        except Exception:
            skill_id = str(task_skill)[:40]
            name = str(task_skill)[:40]

        if not trajectory_summary:
            trajectory_summary = f"Pipeline: {name}"

        # Step 1: Extract action sequence from trajectory
        steps = self._extract_action_steps(trajectory_summary)
        if len(steps) < 2:
            return None

        # Step 2: Abstract parameters (concrete values → variables)
        abstracted_steps = self._abstract_parameters(steps)

        # Step 3: Build condition → action pair
        condition = abstracted_steps[0] if abstracted_steps else ""
        action = " → ".join(abstracted_steps[1:]) if len(abstracted_steps) > 1 else abstracted_steps[0]

        # Step 4: Verify across past runs
        verified_count = await self._verify_across_runs(condition, action)
        confidence = 0.5 + min(0.3, verified_count * 0.1)
        status = "verified" if verified_count >= self._min_verified else "tentative"

        if confidence < self._min_confidence and status != "verified":
            return None

        rule_id = self._make_rule_id(condition, action)
        rule = GeneralizedRule(
            rule_id=rule_id,
            condition=condition,
            action=action,
            abstracted_from=skill_id,
            confidence=confidence,
            verified_count=verified_count,
            status=status,
        )
        self._rules[rule_id] = rule
        _log.info("Generalized rule: %s (%s, confidence=%.2f)", rule_id, status, confidence)
        return rule

    def _extract_action_steps(self, summary: str) -> List[str]:
        steps = []
        action_indicators = [
            r"(?:执行|运行|调用|执行了|调用了|执行命令|执行步骤|step)\s*[:：]*\s*(.+)",
            r"(?:→|->|→|-->) (.+)",
            r"^[-*]\s+(.+)",
        ]
        for pattern in action_indicators:
            for match in re.finditer(pattern, summary, re.MULTILINE):
                step = match.group(1).strip()
                if step and len(step) > 5:
                    steps.append(step)

        if not steps:
            lines = [l.strip() for l in summary.split("\n") if len(l.strip()) > 10]
            steps = lines[:5]

        return steps[:8]

    def _abstract_parameters(self, steps: List[str]) -> List[str]:
        abstracted = []
        for step in steps:
            s = step
            # Replace file paths
            s = re.sub(r"/[\w/.\-]+/[\w.\-]+", "{PATH}", s)
            # Replace IPs
            s = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "{IP}", s)
            # Replace numbers > 100 (likely thresholds, not small counts)
            s = re.sub(r"\b([1-9]\d{2,})\b", "{NUMBER}", s)
            # Replace percentages
            s = re.sub(r"\b\d{1,3}%\b", "{PERCENT}%", s)
            abstracted.append(s)
        return abstracted

    async def _verify_across_runs(self, condition: str, action: str) -> int:
        try:
            from core.harness.learning.experience_vector import get_experience_cache
            cache = get_experience_cache()
            similar = await cache.search(
                f"{condition} {action}",
                top_k=10,
                label="success",
            )
            keyword_match = 0
            cond_words = set(re.findall(r"\w+", condition.lower()))
            act_words = set(re.findall(r"\w+", action.lower()))
            for entry in similar:
                summary = entry.get("summary", "").lower()
                matched = sum(1 for w in cond_words if w in summary) + sum(1 for w in act_words if w in summary)
                if matched >= 2:
                    keyword_match += 1
            return keyword_match
        except Exception:
            return 0

    def _make_rule_id(self, condition: str, action: str) -> str:
        import hashlib
        h = hashlib.md5(f"{condition}|{action}".encode()).hexdigest()[:12]
        return f"rule_{h}"

    def list_rules(self, domain: str = "default", min_confidence: float = 0.0) -> List[GeneralizedRule]:
        return [
            r for r in self._rules.values()
            if r.confidence >= min_confidence and (not domain or r.domain == domain)
        ]

    def list_verified_rules(self) -> List[GeneralizedRule]:
        return [r for r in self._rules.values() if r.status == "verified"]


_success_generalizer: Optional[SuccessGeneralizer] = None


def get_success_generalizer() -> SuccessGeneralizer:
    global _success_generalizer
    if _success_generalizer is None:
        _success_generalizer = SuccessGeneralizer()
    return _success_generalizer
