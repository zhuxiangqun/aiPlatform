"""A2A Agent Card — automatic capability discovery from SkillRegistry and ToolRegistry."""

from dataclasses import dataclass, field
from typing import Dict, List
import logging


@dataclass
class AgentCard:
    name: str = "aiPlat"
    description: str = "企业AI平台 — 303项能力，四层架构（Harness×记忆×知识×编排）"
    version: str = "7.0"
    provider: str = "aiPlat"
    documentation_url: str = ""
    capabilities: Dict[str, bool] = field(default_factory=lambda: {
        "streaming": True,
        "multi_agent": True,
        "orchestration": True,
        "mcp": True,
    })
    skills: List[Dict] = field(default_factory=list)

    @classmethod
    async def from_registry(cls, base_url: str = "") -> "AgentCard":
        """Auto-populate skills from SkillRegistry and ToolRegistry."""
        skills: List[Dict] = []

        try:
            from core.apps.skills.registry import SkillRegistry
            reg = SkillRegistry()
            for name, skill in reg._skills.items():
                enabled = reg._enabled.get(name, True)
                skills.append({
                    "id": name,
                    "name": getattr(skill, 'display_name', name),
                    "category": getattr(skill, 'category', ''),
                    "status": "enabled" if enabled else "disabled",
                    "source": "skill_registry",
                })
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        try:
            from core.apps.tools.discovery import get_tool_registry
            tr = get_tool_registry()
            for tool in tr.list_all():
                skills.append({
                    "id": f"tool:{tool.name}",
                    "name": tool.name,
                    "category": "tool",
                    "status": "enabled",
                    "source": "tool_registry",
                })
        except Exception as e:
            logging.debug(str(e), exc_info=True)

        return cls(
            skills=skills[:50],
            documentation_url=f"{base_url.rstrip('/')}/docs" if base_url else "",
        )

    def to_dict(self) -> Dict:
        return {
            "@context": "https://a2a-protocol.google.com/context/agent.jsonld",
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities,
            "skills": self.skills,
        }
