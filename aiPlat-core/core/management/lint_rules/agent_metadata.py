"""Lint rules for installed workspace agents."""

import os
from pathlib import Path
from typing import Any, List

from core.management.skill_linter_base import LintIssue, LintRule


class AgentFrontmatterCompleteness(LintRule):
    """Check that AGENT.md frontmatter has required + recommended fields."""
    code = "agent_frontmatter"
    level = "warning"
    category = "agent"
    scope = ["agent"]

    REQUIRED = ["name", "agent_type"]
    RECOMMENDED = ["model", "status", "display_name", "description", "category"]

    def check(self, skill: Any) -> List[LintIssue]:
        issues: List[LintIssue] = []
        meta = self._get_metadata(skill)

        for field in self.REQUIRED:
            val = meta.get(field) if isinstance(meta, dict) else None
            if not val:
                issues.append(LintIssue(
                    level="error", code=self.code,
                    message=f"Missing required field: {field}",
                    location=f"frontmatter.{field}",
                ))
        for field in self.RECOMMENDED:
            val = meta.get(field) if isinstance(meta, dict) else None
            if not val:
                issues.append(LintIssue(
                    level=self.level, code=self.code,
                    message=f"Missing recommended field: {field}",
                    location=f"frontmatter.{field}",
                ))
        return issues

    @staticmethod
    def _get_metadata(skill: Any) -> dict:
        md = getattr(skill, "metadata", {}) or {}
        if isinstance(md, dict):
            return md
        return {}


class AgentToolBinding(LintRule):
    """Check that agents have at least skills or tools bound."""
    code = "agent_bare"
    level = "warning"
    category = "agent"
    scope = ["agent"]

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_metadata(skill)
        skills = meta.get("skills") if isinstance(meta, dict) else None
        tools = meta.get("tools") if isinstance(meta, dict) else None
        has_skills = isinstance(skills, list) and len(skills) > 0
        has_tools = isinstance(tools, list) and len(tools) > 0
        if not has_skills and not has_tools:
            return [LintIssue(
                level=self.level, code=self.code,
                message="No skills or tools bound — agent cannot perform actions",
                location="frontmatter.skills+tools",
            )]
        return []

    @staticmethod
    def _get_metadata(skill: Any) -> dict:
        md = getattr(skill, "metadata", {}) or {}
        if isinstance(md, dict):
            return md
        cfg = getattr(skill, "_config", None)
        if cfg:
            return getattr(cfg, "metadata", {}) or {}
        return {}


class AgentSystemPromptCheck(LintRule):
    """Check if agent has system_prompt defined in AGENT.md."""
    code = "agent_system_prompt"
    level = "warning"
    category = "agent"
    scope = ["agent"]

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_metadata(skill)
        prompt = meta.get("system_prompt") if isinstance(meta, dict) else None
        if not prompt:
            return [LintIssue(
                level=self.level, code=self.code,
                message="Missing system_prompt — runtime will use CLAUDE.md as fallback",
                location="frontmatter.system_prompt",
            )]
        return []

    @staticmethod
    def _get_metadata(skill: Any) -> dict:
        return AgentFrontmatterCompleteness._get_metadata(skill)
