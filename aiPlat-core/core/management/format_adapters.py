"""
Format Adapters — detect and convert external agent/skill/MCP/config formats
into aiPlatform native formats during import.

Supported formats:
- agentskills.io (Hermes, Claude Code, Cursor, etc.) → SKILL.md
- Hermes SOUL.md + AGENTS.md → AGENT.md
- Hermes/MCP config JSON → server.yaml
- OpenClaw (via Hermes migration bridge)
"""

from __future__ import annotations
import logging

import json as _json
import os as _os
import shutil as _shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class FormatAdapter(ABC):
    """
    Adapter for converting external formats into aiPlatform native files.
    Subclasses implement detect() and convert().
    """

    NAME: str = "unknown"
    DESCRIPTION: str = ""

    @abstractmethod
    def detect(self, root_dir: Path) -> bool:
        """Return True if this adapter can handle the directory."""
        ...

    @abstractmethod
    def convert(self, root_dir: Path, target_base: Path) -> Dict[str, Any]:
        """
        Convert files in root_dir into aiPlatform format.
        Returns: { converted: [...], skipped: [...], hints: [...] }
        """
        ...


class HermesAdapter(FormatAdapter):
    NAME = "hermes"
    DESCRIPTION = "Hermes Agent (SOUL.md + AGENTS.md + agentskills.io skills + MCP configs)"

    def detect(self, root_dir: Path) -> bool:
        has_hermes = (root_dir / ".hermes").is_dir() or (root_dir / "hermes").is_dir()
        has_soul = (root_dir / "SOUL.md").is_file()
        has_agents_md = (root_dir / "AGENTS.md").is_file()
        has_skills = (root_dir / "skills").is_dir()
        has_mcp = (root_dir / "mcp").is_dir()
        return has_hermes or has_soul or has_agents_md or has_skills or has_mcp

    def convert(self, root_dir: Path, target_base: Path) -> Dict[str, Any]:
        converted: List[str] = []
        skipped: List[str] = []
        hints: List[str] = []

        from core.management.agentskills_parser import (
            convert_agentskills_to_aiplat,
            convert_hermes_so_ul_to_agent_md,
            convert_mcp_json_to_server_yaml,
            is_agentskills_format,
        )

        # Use hermes/ or root_dir as base
        base = root_dir
        if (root_dir / "hermes").is_dir():
            base = root_dir / "hermes"

        # 1. Agent: SOUL.md + AGENTS.md → AGENT.md
        soul = base / "SOUL.md"
        agents = base / "AGENTS.md"
        soul_text = soul.read_text(encoding="utf-8", errors="replace") if soul.is_file() else ""
        agents_text = agents.read_text(encoding="utf-8", errors="replace") if agents.is_file() else ""
        if soul_text or agents_text:
            name = "hermes_agent"
            # Try to derive name from directory
            if base.parent != root_dir and base.name not in (".", "hermes"):
                name = f"hermes_{base.name}"
            agent_md = convert_hermes_so_ul_to_agent_md(soul_text, agents_text, name)
            dest = target_base.parent / "agents" / f"{name}"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "AGENT.md").write_text(agent_md, encoding="utf-8")
            converted.append(f"agent:{name}")
        else:
            skipped.append("agent: no SOUL.md or AGENTS.md found")

        # 2. Skills: agentskills.io → SKILL.md
        skills_dir = base / "skills"
        if skills_dir.is_dir():
            for item in skills_dir.iterdir():
                if not item.is_dir():
                    continue
                skill_md = item / "SKILL.md"
                if not skill_md.is_file():
                    continue
                raw = skill_md.read_text(encoding="utf-8", errors="replace")
                if is_agentskills_format(raw):
                    new_md = convert_agentskills_to_aiplat(raw, item.name)
                    dest = target_base / item.name
                    if dest.exists():
                        dest = target_base / f"{item.name}_hermes"
                    _shutil.copytree(item, dest, dirs_exist_ok=True)
                    (dest / "SKILL.md").write_text(new_md, encoding="utf-8")
                    converted.append(f"skill:{item.name}")
                else:
                    skipped.append(f"skill:{item.name}: already aiPlatform format or unknown")

        # 3. MCP: mcp/*.json → server.yaml
        mcp_dir = base / "mcp"
        if mcp_dir.is_dir():
            for item in mcp_dir.iterdir():
                if item.suffix != ".json":
                    continue
                try:
                    results = convert_mcp_json_to_server_yaml(str(item))
                    for r in results:
                        name = r["name"]
                        dest = target_base.parent / "mcps" / name
                        dest.mkdir(parents=True, exist_ok=True)
                        (dest / "server.yaml").write_text(r["server"], encoding="utf-8")
                        (dest / "policy.yaml").write_text(r["policy"], encoding="utf-8")
                        converted.append(f"mcp:{name}")
                except Exception:
                    hints.append(f"mcp:{item.name}: conversion failed (may need manual review)")

        return {"converted": converted, "skipped": skipped, "hints": hints}


class OpenClawAdapter(FormatAdapter):
    NAME = "openclaw"
    DESCRIPTION = "OpenClaw (Hermes predecessor, uses similar config layout)"

    def detect(self, root_dir: Path) -> bool:
        has_openclaw = (root_dir / ".openclaw").is_dir() or (root_dir / "openclaw").is_dir()
        has_soul = (root_dir / "SOUL.md").is_file()
        has_skills = (root_dir / "skills").is_dir()
        return has_openclaw or has_soul

    def convert(self, root_dir: Path, target_base: Path) -> Dict[str, Any]:
        # OpenClaw uses the same layout as Hermes — delegate to HermesAdapter
        from core.management.agentskills_parser import convert_hermes_so_ul_to_agent_md, is_agentskills_format, convert_agentskills_to_aiplat

        converted: List[str] = []
        skipped: List[str] = []
        base = root_dir
        if (root_dir / ".openclaw").is_dir():
            base = root_dir / ".openclaw"
        elif (root_dir / "openclaw").is_dir():
            base = root_dir / "openclaw"

        # Agent
        soul = base / "SOUL.md"
        if soul.is_file():
            soul_text = soul.read_text(encoding="utf-8", errors="replace")
            name = "openclaw_agent"
            agent_md = convert_hermes_so_ul_to_agent_md(soul_text, "", name)
            dest = target_base.parent / "agents" / name
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "AGENT.md").write_text(agent_md, encoding="utf-8")
            converted.append(f"agent:{name}")
        else:
            skipped.append("agent: no SOUL.md found")

        # Skills
        skills_dir = base / "skills"
        if skills_dir.is_dir():
            for item in skills_dir.iterdir():
                if not item.is_dir():
                    continue
                skill_md = item / "SKILL.md"
                if not skill_md.is_file():
                    continue
                raw = skill_md.read_text(encoding="utf-8", errors="replace")
                if is_agentskills_format(raw):
                    new_md = convert_agentskills_to_aiplat(raw, item.name)
                    dest = target_base / item.name
                    if dest.exists():
                        dest = target_base / f"{item.name}_openclaw"
                    _shutil.copytree(item, dest, dirs_exist_ok=True)
                    (dest / "SKILL.md").write_text(new_md, encoding="utf-8")
                    converted.append(f"skill:{item.name}")

        return {"converted": converted, "skipped": skipped, "hints": []}


# Registry of known format adapters
_FORMAT_ADAPTERS: List[FormatAdapter] = [
    HermesAdapter(),
    OpenClawAdapter(),
]


def get_all_adapters() -> List[Any]:
    """Return all adapters, including lazy-loaded ones."""
    adapters: List[Any] = list(_FORMAT_ADAPTERS)
    try:
        from core.management.coze_adapter import CozeAdapter
        adapters.append(CozeAdapter())
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    try:
        from core.management.dify_adapter import DifyAdapter
        adapters.append(DifyAdapter())
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    try:
        from core.management.n8n_langchain_adapter import N8nAdapter, LangChainAdapter
        adapters.append(N8nAdapter())
        adapters.append(LangChainAdapter())
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return adapters


def detect_and_convert(root_dir: Path, target_skills_base: Path) -> Optional[Dict[str, Any]]:
    """
    Auto-detect external format and convert. Returns None if no adapter matched.
    This is called before the normal SKILL.md/AGENT.md file scanning in AssetInstaller.
    """
    for adapter in get_all_adapters():
        if adapter.detect(root_dir):
            result = adapter.convert(root_dir, target_skills_base)
            result["adapter"] = adapter.NAME
            return result
    return None


__all__ = [
    "FormatAdapter",
    "HermesAdapter",
    "OpenClawAdapter",
    "detect_and_convert",
]
