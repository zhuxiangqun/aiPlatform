u"""
Command Parser — FDE 斜杠命令系统 (v2.8).

Parses "/assess 金融 信贷风险" style commands from AGENT.md frontmatter
and routes them to the corresponding skill invocation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("command_parser")


@dataclass
class Command:
    name: str
    args: List[str] = field(default_factory=list)
    kwargs: Dict[str, str] = field(default_factory=dict)
    skill_name: str = ""
    description: str = ""
    source_agent: str = ""


def parse(text: str) -> Optional[Command]:
    u"""Parse a slash command from user text.

    "/assess 制造 质量追溯" → Command(name="assess", args=["制造","质量追溯"])
    """
    if not text or not text.startswith("/"):
        return None

    text = text.strip()
    parts = text.split()
    if not parts:
        return None

    cmd_name = parts[0][1:]  # strip leading /
    args = parts[1:]

    return Command(name=cmd_name, args=args)


def resolve_skill(
    cmd: Command,
    agent_commands: List[Dict[str, Any]],
) -> Optional[Command]:
    u"""Resolve a parsed command to a skill via AGENT.md commands: frontmatter."""
    for cm in agent_commands:
        if cm.get("name") == cmd.name:
            cmd.skill_name = cm.get("skill", "")
            cmd.description = cm.get("description", "")
            return cmd
    return None


def get_agent_commands(agent_name: str) -> List[Dict[str, Any]]:
    u"""Load command definitions from an agent's AGENT.md frontmatter."""
    import os, yaml

    agent_dir = os.path.expanduser(f"~/.aiplat/agents/{agent_name}")
    agent_md = os.path.join(agent_dir, "AGENT.md")
    if not os.path.exists(agent_md):
        return []

    with open(agent_md) as f:
        content = f.read()

    # Extract YAML frontmatter
    if not content.startswith("---"):
        return []
    parts = content.split("---", 2)
    if len(parts) < 3:
        return []

    try:
        fm = yaml.safe_load(parts[1])
        return fm.get("commands", []) if isinstance(fm, dict) else []
    except Exception:
        return []
