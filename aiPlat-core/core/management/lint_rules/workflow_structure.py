"""Lint rules for installed workflows."""

import os
from pathlib import Path
from typing import Any, List

from core.management.skill_linter_base import LintIssue, LintRule


class WorkflowConfigCompleteness(LintRule):
    """Check that workflow.yaml has required fields."""
    code = "workflow_config"
    level = "warning"
    category = "workflow"
    scope = ["workflow"]

    REQUIRED = ["name"]
    RECOMMENDED = ["trigger", "description", "steps", "version"]

    def check(self, skill: Any) -> List[LintIssue]:
        issues: List[LintIssue] = []
        meta = self._get_metadata(skill)

        for field in self.REQUIRED:
            val = meta.get(field) if isinstance(meta, dict) else None
            if not val:
                issues.append(LintIssue(
                    level="error", code=self.code,
                    message=f"Missing required field: {field}",
                    location=f"workflow.yaml.{field}",
                ))
        for field in self.RECOMMENDED:
            val = meta.get(field) if isinstance(meta, dict) else None
            if not val:
                issues.append(LintIssue(
                    level="info", code=self.code,
                    message=f"Missing recommended field: {field}",
                    location=f"workflow.yaml.{field}",
                ))
        return issues

    @staticmethod
    def _get_metadata(skill: Any) -> dict:
        md = getattr(skill, "metadata", {}) or {}
        if isinstance(md, dict):
            return md
        return {}


class WorkflowTriggerValidation(LintRule):
    """Check that workflow has a valid trigger configuration."""
    code = "workflow_trigger"
    level = "warning"
    category = "workflow"
    scope = ["workflow"]

    VALID_TRIGGERS = {"manual", "cron", "webhook", "event", "on_create", "on_update"}

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_metadata(skill)
        trigger = meta.get("trigger", "").strip().lower() if isinstance(meta, dict) else ""
        if not trigger:
            return [LintIssue(
                level=self.level, code=self.code,
                message="No trigger defined — workflow will never execute automatically",
                location="workflow.yaml.trigger",
            )]
        if trigger not in self.VALID_TRIGGERS:
            return [LintIssue(
                level="info", code=self.code,
                message=f"Trigger '{trigger}' not in common trigger types {sorted(self.VALID_TRIGGERS)} — ensure it is handled",
                location="workflow.yaml.trigger",
            )]
        return []

    @staticmethod
    def _get_metadata(skill: Any) -> dict:
        return WorkflowConfigCompleteness._get_metadata(skill)


class WorkflowStepsCheck(LintRule):
    """Check that workflow has defined execution steps."""
    code = "workflow_steps"
    level = "warning"
    category = "workflow"
    scope = ["workflow"]

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_metadata(skill)
        steps = meta.get("steps") if isinstance(meta, dict) else None
        if not isinstance(steps, list) or len(steps) == 0:
            return [LintIssue(
                level=self.level, code=self.code,
                message="No steps defined — workflow has no execution logic",
                location="workflow.yaml.steps",
            )]
        return []

    @staticmethod
    def _get_metadata(skill: Any) -> dict:
        return WorkflowConfigCompleteness._get_metadata(skill)
