"""Lint rules for installed MCP servers."""

import os
from pathlib import Path
from typing import Any, List

from core.management.skill_linter_base import LintIssue, LintRule


class McpConfigCompleteness(LintRule):
    """Check that server.yaml has required fields."""
    code = "mcp_config"
    level = "warning"
    category = "mcp"
    scope = ["mcp"]

    REQUIRED = ["name", "transport"]
    RECOMMENDED = ["command", "args", "url", "description"]

    def check(self, skill: Any) -> List[LintIssue]:
        issues: List[LintIssue] = []
        meta = self._get_metadata(skill)

        for field in self.REQUIRED:
            val = meta.get(field) if isinstance(meta, dict) else None
            if not val:
                issues.append(LintIssue(
                    level="error", code=self.code,
                    message=f"Missing required field: {field}",
                    location=f"server.yaml.{field}",
                ))
        for field in self.RECOMMENDED:
            val = meta.get(field) if isinstance(meta, dict) else None
            if not val:
                issues.append(LintIssue(
                    level="info", code=self.code,
                    message=f"Missing recommended field: {field}",
                    location=f"server.yaml.{field}",
                ))
        return issues

    @staticmethod
    def _get_metadata(skill: Any) -> dict:
        md = getattr(skill, "metadata", {}) or {}
        if isinstance(md, dict):
            return md
        return {}


class McpPolicyFileCheck(LintRule):
    """Check that policy.yaml exists alongside server.yaml."""
    code = "mcp_policy"
    level = "warning"
    category = "mcp"
    scope = ["mcp"]

    def check(self, skill: Any) -> List[LintIssue]:
        skill_dir = self._resolve_dir(skill)
        if not skill_dir:
            return []
        root = Path(skill_dir)
        has_server = (root / "server.yaml").exists()
        has_policy = (root / "policy.yaml").exists()
        if has_server and not has_policy:
            return [LintIssue(
                level=self.level, code=self.code,
                message="server.yaml exists but no policy.yaml — tools will have default deny-all policy",
                location=str(root / "policy.yaml"),
            )]
        return []

    @staticmethod
    def _resolve_dir(skill: Any) -> str:
        md = getattr(skill, "metadata", {}) or {}
        if isinstance(md, dict):
            for k in ("skill_dir", "mcp_dir", "fs", "filesystem"):
                v = md.get(k)
                if isinstance(v, str) and os.path.isdir(v):
                    return v
                if isinstance(v, dict):
                    d = v.get("skill_dir") or v.get("mcp_dir") or v.get("root")
                    if isinstance(d, str) and os.path.isdir(d):
                        return d
        return ""


class McpTransportValidation(LintRule):
    """Validate MCP transport configuration."""
    code = "mcp_transport"
    level = "error"
    category = "mcp"
    scope = ["mcp"]

    def check(self, skill: Any) -> List[LintIssue]:
        meta = self._get_metadata(skill)
        transport = meta.get("transport", "").strip().lower() if isinstance(meta, dict) else ""
        command = meta.get("command", "").strip() if isinstance(meta, dict) else ""
        url = meta.get("url", "").strip() if isinstance(meta, dict) else ""

        if transport == "stdio" and not command:
            return [LintIssue(
                level=self.level, code=self.code,
                message="stdio transport requires 'command' field in server.yaml",
                location="server.yaml.command",
            )]
        if transport in ("sse", "http") and not url:
            return [LintIssue(
                level=self.level, code=self.code,
                message=f"{transport} transport requires 'url' field in server.yaml",
                location="server.yaml.url",
            )]
        return []

    @staticmethod
    def _get_metadata(skill: Any) -> dict:
        return McpConfigCompleteness._get_metadata(skill)
