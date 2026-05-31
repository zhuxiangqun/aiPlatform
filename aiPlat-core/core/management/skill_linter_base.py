"""
Skill Linter — extensible rule engine.

Architecture:
  - Simple checks → YAML config (lint_rules.yaml) → YAMLRule
  - Complex checks → Python classes (lint_rules/*.py) → LintRule subclass
  - Both feed into RuleRegistry → lint_skill() facade

Adding a new rule:
  - Simple: add 5 lines to lint_rules.yaml, zero code change
  - Complex: create a class in lint_rules/, auto-discovered, zero touch to existing code
"""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================
# Data classes (shared with skill_linter.py facade)
# ============================================================

@dataclass
class LintIssue:
    level: str  # error | warning
    code: str
    message: str
    location: Optional[str] = None


@dataclass
class LintReport:
    skill_id: str
    risk_level: str  # low | medium | high
    blocked: bool
    errors: List[LintIssue] = field(default_factory=list)
    warnings: List[LintIssue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["errors"] = [asdict(x) for x in self.errors]
        d["warnings"] = [asdict(x) for x in self.warnings]
        d["summary"] = {
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "risk_level": self.risk_level,
            "blocked": self.blocked,
        }
        return d


@dataclass
class FixProposal:
    fix_id: str
    issue_code: str
    title: str
    priority: str  # P0 | P1 | P2
    risk_level: str
    auto_applicable: bool
    requires_approval: bool
    touches: List[str]
    ops: List[Dict[str, Any]]
    preview: Dict[str, str]
    markdown: str


# ============================================================
# Rule base classes
# ============================================================

class LintRule:
    """Base class for all lint rules. Each rule checks one aspect of a skill."""

    code: str = ""
    level: str = "warning"  # error | warning
    category: str = "metadata"  # metadata | trigger | schema | governance | sop

    def check(self, skill: Any) -> List[LintIssue]:
        """Run the check and return a list of issues found."""
        raise NotImplementedError

    def propose_fix(self, skill: Any, issue: LintIssue) -> Optional[FixProposal]:
        """Optionally propose an auto-fix for a detected issue."""
        return None

    # ---- helpers for subclasses ----

    @staticmethod
    def _get_field(skill: Any, path: str) -> Any:
        """Access nested field: name→skill.name, output_schema.markdown→skill.output_schema['markdown']"""
        value = skill
        for part in path.split("."):
            if value is None:
                return None
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
        return value

    @staticmethod
    def _as_list(x: Any) -> List[str]:
        if x is None:
            return []
        if isinstance(x, str):
            s = x.strip()
            return [s] if s else []
        if isinstance(x, list):
            return [str(it).strip() for it in x if str(it).strip()]
        return []

    def _issue(self, message: str, location: str = "") -> LintIssue:
        return LintIssue(level=self.level, code=self.code, message=message, location=location or self.code)


# ============================================================
# YAML-driven declarative rule engine
# ============================================================

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

class YAMLRule(LintRule):
    """
    Declarative rule driven by YAML config (lint_rules.yaml).

    Supported check types:
      - field_required:     path must exist and be truthy
      - field_enum:         value must be in 'allowed' list
      - field_pattern:      value must match 'pattern' regex
      - field_length_range: length in [min, max]
      - field_not_empty:    list/dict/string is non-empty

    Optional 'when' clause for conditional checks:
      when:
        field: output_schema
        not_empty: true       # or 'exists: true', 'equals: <value>'
    """

    def __init__(self, rule_def: Dict[str, Any]):
        self._def = rule_def
        self.code = rule_def.get("id", "")
        self.level = rule_def.get("level", "warning")
        self.category = rule_def.get("category", "metadata")
        self._check_def = rule_def.get("check", {})
        self._check_type = self._check_def.get("type", "")
        self._check_path = self._check_def.get("path", "")
        self._when = self._check_def.get("when")
        # Custom message override
        self._message = rule_def.get("message")

    def check(self, skill: Any) -> List[LintIssue]:
        # Conditional gate
        if self._when and not self._eval_when(skill, self._when):
            return []

        dispatcher = {
            "field_required": self._check_required,
            "field_enum": self._check_enum,
            "field_pattern": self._check_pattern,
            "field_length_range": self._check_length,
            "field_not_empty": self._check_not_empty,
        }
        handler = dispatcher.get(self._check_type)
        if handler:
            try:
                return handler(skill)
            except Exception:
                pass
        return []

    def propose_fix(self, skill: Any, issue: LintIssue) -> Optional[FixProposal]:
        fix_def = self._def.get("fix")
        if not fix_def:
            return None
        return FixProposal(
            fix_id=fix_def.get("fix_id", f"fix_{self.code}"),
            issue_code=self.code,
            title=fix_def.get("title", ""),
            priority=fix_def.get("priority", "P1"),
            risk_level=fix_def.get("risk_level", "low"),
            auto_applicable=fix_def.get("auto", False),
            requires_approval=fix_def.get("requires_approval", False),
            touches=fix_def.get("touches", []),
            ops=fix_def.get("ops", []),
            preview={"before_snippet": "", "after_snippet": ""},
            markdown=fix_def.get("md", ""),
        )

    # ---- when clause evaluator ----

    def _eval_when(self, skill: Any, when: Dict[str, Any]) -> bool:
        wf = when.get("field", "")
        if not wf:
            return True
        v = self._get_field(skill, wf)
        if "not_empty" in when and when["not_empty"]:
            if v is None:
                return False
            if isinstance(v, (str, list, dict)) and not v:
                return False
            return True
        if "exists" in when:
            return (v is not None) == bool(when["exists"])
        if "equals" in when:
            return v == when["equals"]
        return True

    # ---- check type handlers ----

    def _check_required(self, skill: Any) -> List[LintIssue]:
        value = self._get_field(skill, self._check_path)
        if not value:
            msg = self._message or f"缺少 {self._check_path}"
            return [self._issue(msg, f"frontmatter.{self._check_path}")]
        return []

    def _check_enum(self, skill: Any) -> List[LintIssue]:
        value = self._get_field(skill, self._check_path)
        allowed = set(self._check_def.get("allowed", []))
        if value and value not in allowed:
            msg = self._message or f"category='{value}' 不在推荐枚举内（不影响运行，但建议统一）"
            return [self._issue(msg, f"frontmatter.{self._check_path}")]
        return []

    def _check_pattern(self, skill: Any) -> List[LintIssue]:
        value = self._get_field(skill, self._check_path)
        pattern = self._check_def.get("pattern", "")
        if value and pattern:
            v = str(value).lstrip("v")
            if not re.match(pattern, v):
                msg = self._message or f"version='{value}' 不是标准 semver（建议 1.2.3）"
                return [self._issue(msg, f"frontmatter.{self._check_path}")]
        return []

    def _check_length(self, skill: Any) -> List[LintIssue]:
        value = self._get_field(skill, self._check_path)
        if not value:
            return []
        length = len(str(value))
        min_l = self._check_def.get("min", 0)
        max_l = self._check_def.get("max", float("inf"))
        if length < min_l:
            msg = self._message or f"description 过短，可能影响路由命中与可解释性（建议 >= 8 字）"
            return [self._issue(msg, f"frontmatter.{self._check_path}")]
        if length > max_l:
            msg = self._message or f"description 过长（建议 <= 280 字），避免 L1 噪声影响匹配"
            return [self._issue(msg, f"frontmatter.{self._check_path}")]
        return []

    def _check_not_empty(self, skill: Any) -> List[LintIssue]:
        value = self._get_field(skill, self._check_path)
        if value is None or (isinstance(value, (str, list, dict)) and not value):
            msg = self._message or f"缺少 {self._check_path}"
            return [self._issue(msg, f"frontmatter.{self._check_path}")]
        return []


# ============================================================
# Rule Registry
# ============================================================

class RuleRegistry:
    """Collects all lint rules (YAML + Python) and runs them against a skill."""

    def __init__(self):
        self._rules: List[LintRule] = []

    def register(self, rule: LintRule) -> None:
        self._rules.append(rule)

    def discover(self) -> None:
        """Auto-discover all rules: YAML config + Python classes in lint_rules/"""
        self._load_yaml_rules()
        self._load_python_rules()

    def run_all(self, skill: Any) -> LintReport:
        """Run all rules against a skill, return aggregated report."""
        from core.management.skill_linter import risk_level_from_permissions

        sid = ""
        try:
            sid = str(getattr(skill, "id", "") or (skill.get("id") if isinstance(skill, dict) else "")).strip()
        except Exception:
            sid = ""
        sid = sid or "<unknown>"

        errors: List[LintIssue] = []
        warnings: List[LintIssue] = []

        for rule in self._rules:
            try:
                issues = rule.check(skill)
                for issue in issues:
                    if issue.level == "error":
                        errors.append(issue)
                    else:
                        warnings.append(issue)
            except Exception:
                pass

        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        meta = meta if isinstance(meta, dict) else {}
        perms = LintRule._as_list(meta.get("permissions") or meta.get("permission"))
        risk = risk_level_from_permissions(perms)
        blocked = bool(risk == "high" and len(errors) > 0)

        return LintReport(skill_id=sid, risk_level=risk, blocked=blocked, errors=errors, warnings=warnings)

    def propose_fixes(self, skill: Any, lint: Dict[str, Any]) -> List[FixProposal]:
        """Generate fix proposals by asking each rule that reported an issue."""
        errors = lint.get("errors") if isinstance(lint, dict) else []
        warnings = lint.get("warnings") if isinstance(lint, dict) else []
        codes = {str(x.get("code") or "").strip() for x in (errors or []) if isinstance(x, dict)}
        codes |= {str(x.get("code") or "").strip() for x in (warnings or []) if isinstance(x, dict)}
        codes.discard("")

        fixes: List[FixProposal] = []
        for rule in self._rules:
            if rule.code in codes:
                try:
                    matching = [x for x in (errors + warnings) if isinstance(x, dict) and x.get("code") == rule.code]
                    if matching:
                        item = matching[0]
                        lint_issue = LintIssue(
                            level=item.get("level", "warning"),
                            code=item.get("code", ""),
                            message=item.get("message", ""),
                            location=item.get("location"),
                        )
                        fix = rule.propose_fix(skill, lint_issue)
                        if fix:
                            fixes.append(fix)
                except Exception:
                    pass
        return fixes

    # ---- discovery ----

    def _load_yaml_rules(self) -> None:
        config_paths = [
            Path(__file__).parent / "lint_rules.yaml",
            Path(os.path.expanduser("~/.aiplat/lint_rules.yaml")),
        ]
        for cfg_path in config_paths:
            if not cfg_path.exists():
                continue
            try:
                import yaml
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for rule_def in data.get("rules", []):
                    self.register(YAMLRule(rule_def))
            except Exception:
                pass

    def _load_python_rules(self) -> None:
        rules_pkg = Path(__file__).parent / "lint_rules"
        if not rules_pkg.is_dir():
            return
        try:
            for item in sorted(rules_pkg.iterdir()):
                if item.suffix != ".py" or item.name.startswith("_"):
                    continue
                module_name = item.stem
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"core.management.lint_rules.{module_name}",
                        str(item)
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type)
                                    and issubclass(attr, LintRule)
                                    and attr is not LintRule
                                    and attr is not YAMLRule
                                    and not attr.__name__.startswith("_")):
                                self.register(attr())
                except Exception:
                    pass
        except Exception:
            pass


# ============================================================
# Singleton (lazy init)
# ============================================================

_registry: Optional[RuleRegistry] = None


def get_registry() -> RuleRegistry:
    global _registry
    if _registry is None:
        _registry = RuleRegistry()
        _registry.discover()
    return _registry
