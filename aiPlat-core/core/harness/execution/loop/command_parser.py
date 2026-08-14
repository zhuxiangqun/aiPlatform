u"""
Command Parser — FDE slash-command system (v2.8).

Parses "/assess finance credit-risk" style commands from AGENT.md frontmatter
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

    "/assess manufacturing quality-traceability" → Command(name="assess", args=["manufacturing","quality-traceability"])
    "/moa --preset security analyze-this-code" → Command(name="moa", args=["analyze-this-code"], kwargs={"preset":"security"})
    """
    if not text or not text.startswith("/"):
        return None

    text = text.strip()
    parts = text.split()
    if not parts:
        return None

    cmd_name = parts[0][1:]  # strip leading /
    raw_args = parts[1:]

    kwargs: Dict[str, str] = {}
    args: List[str] = []
    i = 0
    while i < len(raw_args):
        if raw_args[i].startswith("--") and i + 1 < len(raw_args):
            kwargs[raw_args[i][2:]] = raw_args[i + 1]
            i += 2
        else:
            args.append(raw_args[i])
            i += 1

    return Command(name=cmd_name, args=args, kwargs=kwargs)


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
