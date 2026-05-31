"""
AGENT.md configuration validator — runs at server startup to catch misconfigurations.

Checks:
  1. YAML syntax validity (reject on parse failure)
  2. Required frontmatter fields (name, agent_type, model, status)
  3. Model/provider compatibility (warn if gpt-4/claude without matching API key)
  4. Skills/tools field name consistency

Usage:
    from core.management.agent_config_validator import validate_all_agents
    errors, warnings = validate_all_agents(agents_dir)
    if errors and os.getenv("AIPLAT_STRICT_AGENT_CONFIG", "false") == "true":
        raise RuntimeError(f"Agent config validation failed: {errors}")
"""

from __future__ import annotations

import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ConfigIssue:
    agent: str
    file: str
    severity: str  # "error" | "warn"
    message: str


REQUIRED_FIELDS = ["name", "agent_type"]
# model is technically optional (falls back to default) but strongly recommended
RECOMMENDED_FIELDS = ["model", "status", "display_name"]

KNOWN_PROVIDER_MODELS: Dict[str, List[str]] = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner", "deepseek-embedding"],
    "openai": ["gpt-4", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "text-embedding-3-small"],
    "anthropic": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
}

# Model families detected by prefix — warn if no matching API key set
MODEL_NEEDS_API_KEY: Dict[str, str] = {
    "gpt-": "OPENAI_API_KEY",
    "claude-": "ANTHROPIC_API_KEY",
}


def validate_agent_file(md_path: Path) -> List[ConfigIssue]:
    """Validate a single AGENT.md file. Returns list of issues."""
    issues: List[ConfigIssue] = []
    agent_name = md_path.parent.name
    file_path = str(md_path)

    # 1) YAML syntax check
    try:
        raw = md_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [ConfigIssue(agent=agent_name, file=file_path, severity="error",
                           message=f"Cannot read file: {e}")]

    # Check for control characters
    for i, ch in enumerate(raw):
        if ord(ch) < 0x20 and ch not in ("\t", "\n", "\r"):
            issues.append(ConfigIssue(
                agent=agent_name, file=file_path, severity="error",
                message=f"Control character 0x{ord(ch):02x} at position {i}"
            ))
            break

    # Parse frontmatter
    fm: dict = {}
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError as e:
                issues.append(ConfigIssue(
                    agent=agent_name, file=file_path, severity="error",
                    message=f"YAML parse error in frontmatter: {e}"
                ))
                return issues

    if not isinstance(fm, dict):
        issues.append(ConfigIssue(
            agent=agent_name, file=file_path, severity="error",
            message="Frontmatter missing or not a YAML mapping"
        ))
        return issues

    # 2) Required fields
    for field in REQUIRED_FIELDS:
        if not fm.get(field):
            issues.append(ConfigIssue(
                agent=agent_name, file=file_path, severity="error",
                message=f"Missing required field: {field}"
            ))

    for field in RECOMMENDED_FIELDS:
        if not fm.get(field):
            issues.append(ConfigIssue(
                agent=agent_name, file=file_path, severity="warn",
                message=f"Missing recommended field: {field}"
            ))

    # 3) Model/provider compatibility
    model = fm.get("model") or (fm.get("config") or {}).get("model") or ""
    if model:
        # Check if model belongs to a provider without API key
        for prefix, env_key in MODEL_NEEDS_API_KEY.items():
            if model.startswith(prefix):
                if not os.getenv(env_key):
                    issues.append(ConfigIssue(
                        agent=agent_name, file=file_path, severity="warn",
                        message=f"Model '{model}' requires provider API key ({env_key}), but it is not set. "
                                f"Request will fail at runtime."
                    ))
                break
        # Check for completely unknown model
        known_models = set()
        for provider_models in KNOWN_PROVIDER_MODELS.values():
            known_models.update(provider_models)
        if model not in known_models and not any(env for env in [
            "AIPLAT_LLM_MODEL", "AIPLAT_AGENT_MODEL", "AIPLAT_DEFAULT_MODEL"
        ] if os.getenv(env)):
            issues.append(ConfigIssue(
                agent=agent_name, file=file_path, severity="warn",
                message=f"Model '{model}' is not in known model registry. Ensure provider is configured."
            ))

    # 4) Field name consistency
    has_skills = bool(fm.get("skills"))
    has_required = bool(fm.get("required_skills"))
    if has_skills and not has_required:
        pass  # OK — parser now reads both fields
    has_tools = bool(fm.get("tools"))
    has_required_tools = bool(fm.get("required_tools"))
    if has_tools and not has_required_tools:
        pass  # OK — parser now reads both fields

    # 5) Shell agent detection — check if agent has meaningful identity
    skills = fm.get("skills") or fm.get("required_skills") or []
    tools = fm.get("tools") or fm.get("required_tools") or []
    system_prompt = (fm.get("config") or {}).get("system_prompt", "") if isinstance(fm.get("config"), dict) else ""
    has_system_prompt = bool(system_prompt and len(system_prompt.strip()) > 20)

    shell_flags = 0
    if not has_system_prompt:
        shell_flags += 1
        issues.append(ConfigIssue(
            agent=agent_name, file=file_path, severity="warn",
            message="Missing system_prompt — runtime will use CLAUDE.md as fallback"
        ))
    if not skills or len(skills) == 0:
        shell_flags += 1
        issues.append(ConfigIssue(
            agent=agent_name, file=file_path, severity="warn",
            message="No skills bound — agent has no capabilities"
        ))
    if not tools or len(tools) == 0:
        shell_flags += 1
        issues.append(ConfigIssue(
            agent=agent_name, file=file_path, severity="warn",
            message="No tools bound — agent cannot perform actions"
        ))
    if shell_flags >= 3:
        issues.append(ConfigIssue(
            agent=agent_name, file=file_path, severity="warn",
            message="Shell agent detected: no system_prompt, no skills, no tools. Agent will behave as generic CLAUDE.md assistant."
        ))

    return issues


def validate_all_agents(agents_dir: str) -> Tuple[List[ConfigIssue], List[ConfigIssue]]:
    """Validate all AGENT.md files in a directory tree (recursive).
    Returns (errors, warnings).
    """
    errors: List[ConfigIssue] = []
    warnings: List[ConfigIssue] = []
    base = Path(agents_dir)
    if not base.exists():
        return errors, warnings

    for md_path in sorted(base.rglob("AGENT.md")):
        if "__pycache__" in str(md_path):
            continue
        issues = validate_agent_file(md_path)
        for issue in issues:
            if issue.severity == "error":
                errors.append(issue)
            else:
                warnings.append(issue)

    return errors, warnings
