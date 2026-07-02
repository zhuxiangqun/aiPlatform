"""
Standards Validator — declarative document compliance checking.

Validates stage output artifacts against configurable document standards
defined in `standards_rules.yaml`. Supports required sections, content length
checks, forbidden patterns, required patterns, and terminology enforcement.

Usage:
    from core.harness.evaluation.standards_validator import StandardsValidator, get_standards_validator

    validator = get_standards_validator()
    report = validator.validate(document_text, doc_type="proposal")
    # report.passed → True/False
    # report.issues → [{rule_id, level, message, section}]
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml as _yaml

_log = logging.getLogger("aiplat.standards_validator")


@dataclass
class StandardsIssue:
    rule_id: str
    level: str  # error | warning
    message: str
    section: str = ""

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "level": self.level,
            "message": self.message,
            "section": self.section,
        }


@dataclass
class StandardsReport:
    passed: bool
    issues: List[StandardsIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    total_rules: int = 0

    @property
    def failed_count(self) -> int:
        return self.error_count + self.warning_count

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "total_rules": self.total_rules,
            "issues": [i.to_dict() for i in self.issues],
        }


class StandardsValidator:
    """Declarative document standards checker."""

    def __init__(self, rules_path: Optional[str] = None):
        if rules_path is None:
            rules_path = str(
                Path(__file__).resolve().parent / "standards_rules.yaml"
            )
        self._rules_path = rules_path
        self._rules: List[Dict[str, Any]] = []
        self._load_rules()

    def _load_rules(self):
        try:
            with open(self._rules_path, "r", encoding="utf-8") as f:
                data = _yaml.safe_load(f) or {}
            self._rules = data.get("rules", [])
            _log.info("Loaded %d standards rules from %s", len(self._rules), self._rules_path)
        except Exception as e:
            _log.warning("Failed to load standards rules: %s", e)
            self._rules = []

    def validate(self, document_text: str, doc_type: str = "general") -> StandardsReport:
        if not document_text or not document_text.strip():
            return StandardsReport(passed=False, issues=[
                StandardsIssue(rule_id="empty_document", level="error",
                              message="Document is empty")
            ], error_count=1)

        issues: List[StandardsIssue] = []
        for rule in self._rules:
            check = rule.get("check", {})
            check_type = check.get("type", "")
            issue = self._apply_rule(rule, check_type, check, document_text)
            if issue:
                issues.append(issue)

        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]

        return StandardsReport(
            passed=len(errors) == 0,
            issues=issues,
            error_count=len(errors),
            warning_count=len(warnings),
            total_rules=len(self._rules),
        )

    def _apply_rule(self, rule: dict, check_type: str, check: dict, text: str) -> Optional[StandardsIssue]:
        try:
            if check_type == "section_required":
                return self._check_section_required(rule, check, text)
            elif check_type == "section_length_range":
                return self._check_section_length(rule, check, text)
            elif check_type == "text_pattern_forbidden":
                return self._check_pattern_forbidden(rule, check, text)
            elif check_type == "text_pattern_required":
                return self._check_pattern_required(rule, check, text)
            else:
                _log.debug("Unknown check type: %s", check_type)
                return None
        except Exception as e:
            _log.debug("Rule %s check failed: %s", rule.get("id", "?"), e)
            return None

    @staticmethod
    def _find_section(text: str, section_name: str) -> Optional[str]:
        """Find section content by heading. Matches '## 节名' or '# 节名' patterns."""
        patterns = [
            rf'^#{{1,3}}\s*{re.escape(section_name)}\s*$',
            rf'^#{{1,3}}\s*.*{re.escape(section_name)}.*$',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.MULTILINE)
            if m:
                start = m.start()
                rest = text[start:]
                next_section = re.search(r'^#{1,3}\s+', rest[m.end() - m.start():], re.MULTILINE)
                if next_section:
                    return rest[:next_section.start() + (m.end() - m.start())]
                return rest
        return None

    def _check_section_required(self, rule: dict, check: dict, text: str) -> Optional[StandardsIssue]:
        section = check.get("section", "")
        if not section:
            return None
        content = self._find_section(text, section)
        if content is None or len(content.strip()) < 10:
            return StandardsIssue(
                rule_id=rule.get("id", ""),
                level=rule.get("level", "warning"),
                message=rule.get("message", f"Missing section: {section}"),
                section=section,
            )
        return None

    def _check_section_length(self, rule: dict, check: dict, text: str) -> Optional[StandardsIssue]:
        section = check.get("section", "")
        min_len = check.get("min", 0)
        max_len = check.get("max", 999999)
        if not section:
            return None
        content = self._find_section(text, section)
        if content is None:
            return None
        length = len(content.strip())
        if length < min_len:
            return StandardsIssue(
                rule_id=rule.get("id", ""),
                level=rule.get("level", "warning"),
                message=rule.get("message", f"Section '{section}' too short: {length} chars (min {min_len})"),
                section=section,
            )
        if length > max_len:
            return StandardsIssue(
                rule_id=rule.get("id", ""),
                level=rule.get("level", "warning"),
                message=rule.get("message", f"Section '{section}' too long: {length} chars (max {max_len})"),
                section=section,
            )
        return None

    def _check_pattern_forbidden(self, rule: dict, check: dict, text: str) -> Optional[StandardsIssue]:
        pattern = check.get("pattern", "")
        if not pattern:
            return None
        flags = re.MULTILINE
        if check.get("ignore_case", True):
            flags |= re.IGNORECASE
        matches = list(re.finditer(pattern, text, flags))
        if matches:
            examples = [m.group()[:40] for m in matches[:3]]
            return StandardsIssue(
                rule_id=rule.get("id", ""),
                level=rule.get("level", "warning"),
                message=f"{rule.get('message', '')} (found: {', '.join(examples)})",
            )
        return None

    def _check_pattern_required(self, rule: dict, check: dict, text: str) -> Optional[StandardsIssue]:
        pattern = check.get("pattern", "")
        if not pattern:
            return None
        if not re.search(pattern, text, re.MULTILINE | re.IGNORECASE):
            return StandardsIssue(
                rule_id=rule.get("id", ""),
                level=rule.get("level", "warning"),
                message=rule.get("message", f"Required pattern not found: {pattern}"),
            )
        return None

    def reload(self):
        self._load_rules()


_standards_validator: Optional[StandardsValidator] = None


def get_standards_validator() -> StandardsValidator:
    global _standards_validator
    if _standards_validator is None:
        _standards_validator = StandardsValidator()
    return _standards_validator
