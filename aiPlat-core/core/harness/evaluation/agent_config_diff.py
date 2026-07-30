"""Agent Config Diff — structured change detection for AGENT.md frontmatter.

Returns a human-readable diff between two versions of an agent's configuration.
Used by HITL review workflows to show approvers exactly what changed.

Usage:
    differ = AgentConfigDiffer()
    diff = differ.diff_versions(old_yaml, new_yaml)
    # → {added: {}, removed: {}, changed: {}, summary: "..."}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConfigDiff:
    added: Dict[str, Any] = field(default_factory=dict)
    removed: Dict[str, Any] = field(default_factory=dict)
    changed: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    summary: str = ""
    risk_level: str = "low"  # low/medium/high


class AgentConfigDiffer:
    """Compare two AGENT.md frontmatter versions and produce structured diff."""

    DIFFABLE_FIELDS = {
        "model", "system_prompt", "required_skills", "required_tools",
        "output_artifact", "input_artifacts", "phase", "hitl_phase",
        "auto_hitl", "status", "agent_type", "version", "description",
        "display_name", "config",
    }

    HIGH_RISK_FIELDS = {"model", "auto_hitl", "status", "agent_type"}

    def diff_versions(self, old_fm: Dict[str, Any], new_fm: Dict[str, Any]) -> ConfigDiff:
        """Compare two frontmatter dicts and produce structured diff."""
        diff = ConfigDiff()

        for field in self.DIFFABLE_FIELDS:
            old_val = old_fm.get(field)
            new_val = new_fm.get(field)

            if old_val is None and new_val is not None:
                diff.added[field] = new_val
            elif old_val is not None and new_val is None:
                diff.removed[field] = old_val
            elif old_val != new_val:
                diff.changed[field] = {"from": old_val, "to": new_val}

        # Build summary
        parts = []
        if diff.added:
            parts.append(f"新增: {', '.join(diff.added.keys())}")
        if diff.removed:
            parts.append(f"移除: {', '.join(diff.removed.keys())}")
        if diff.changed:
            changed_fields = list(diff.changed.keys())
            parts.append(f"修改: {', '.join(changed_fields[:5])}")
            if len(changed_fields) > 5:
                parts[-1] += f" +{len(changed_fields)-5} 项"

        diff.summary = "; ".join(parts) if parts else "无变更"

        # Risk assessment
        high_risk_changes = [k for k in diff.changed if k in self.HIGH_RISK_FIELDS]
        high_risk_added = [k for k in diff.added if k in self.HIGH_RISK_FIELDS]
        high_risk_removed = [k for k in diff.removed if k in self.HIGH_RISK_FIELDS]

        if "model" in high_risk_changes or "model" in high_risk_added:
            diff.risk_level = "high"
        elif high_risk_changes or high_risk_added or high_risk_removed:
            diff.risk_level = "medium"
        else:
            diff.risk_level = "low"

        return diff

    def diff_from_files(self, old_content: str, new_content: str) -> ConfigDiff:
        """Parse AGENT.md content strings and diff their frontmatter."""
        import yaml

        def _parse_frontmatter(text: str) -> Dict[str, Any]:
            if not text.startswith("---"):
                return {}
            parts = text.split("---", 2)
            if len(parts) < 3:
                return {}
            try:
                return yaml.safe_load(parts[1]) or {}
            except Exception:
                return {}

        old_fm = _parse_frontmatter(old_content)
        new_fm = _parse_frontmatter(new_content)
        return self.diff_versions(old_fm, new_fm)


def compute_agent_diff(old_content: str, new_content: str) -> Dict[str, Any]:
    """Convenience function for calling from API endpoints."""
    differ = AgentConfigDiffer()
    diff = differ.diff_from_files(old_content, new_content)
    return {
        "added": diff.added,
        "removed": diff.removed,
        "changed": diff.changed,
        "summary": diff.summary,
        "risk_level": diff.risk_level,
    }
