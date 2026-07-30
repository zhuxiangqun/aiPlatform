"""Multi-framework Export — convert SKILL.md/AGENT.md to external tool specifications.

Exports aiPlat skill definitions to industry-standard formats:
- OpenAI function calling spec
- LangChain tool spec
- Anthropic tool use spec

Usage:
    exporter = SkillExporter()
    openai_spec = exporter.to_openai(skill_md_content)
    langchain_spec = exporter.to_langchain(skill_md_content)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json as _json


class SkillExporter:
    """Export aiPlat SKILL.md declarations to external framework specs."""

    def to_openai(self, skill_md_content: str) -> Dict[str, Any]:
        """Convert SKILL.md → OpenAI function calling specification."""
        fm = self._parse_frontmatter(skill_md_content)
        if not fm:
            return {}

        name = fm.get("name", "unknown_skill")
        desc = fm.get("description", fm.get("display_name", ""))
        input_schema = fm.get("input_schema", {}) or {}

        properties = {}
        required = []
        if isinstance(input_schema, dict):
            for prop_name, prop_def in input_schema.get("properties", {}).items():
                ptype = prop_def.get("type", "string")
                pdesc = prop_def.get("description", "")
                properties[prop_name] = {"type": ptype, "description": pdesc}
            required = input_schema.get("required", [])

        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_langchain(self, skill_md_content: str) -> Dict[str, Any]:
        """Convert SKILL.md → LangChain tool specification."""
        fm = self._parse_frontmatter(skill_md_content)
        if not fm:
            return {}

        name = fm.get("name", "unknown_skill")
        desc = fm.get("description", fm.get("display_name", ""))
        input_schema = fm.get("input_schema", {}) or {}
        output_schema = fm.get("output_schema", {}) or {}

        return {
            "name": name,
            "description": desc,
            "args_schema": input_schema,
            "return_schema": output_schema,
            "metadata": {
                "version": fm.get("version", "1.0.0"),
                "category": fm.get("category", ""),
                "execution_type": fm.get("execution_type", "prompt"),
                "effects": fm.get("effects", []),
                "triggers": fm.get("triggers", []),
            },
        }

    def to_anthropic(self, skill_md_content: str) -> Dict[str, Any]:
        """Convert SKILL.md → Anthropic tool use specification."""
        fm = self._parse_frontmatter(skill_md_content)
        if not fm:
            return {}

        name = fm.get("name", "unknown_skill")
        desc = fm.get("description", fm.get("display_name", ""))
        input_schema = fm.get("input_schema", {}) or {}
        input_schema["title"] = name
        input_schema["description"] = desc

        return {
            "name": name,
            "description": desc,
            "input_schema": input_schema,
        }

    def export_all(self, skill_md_content: str, format: str = "all") -> Dict[str, Any]:
        """Export to requested format(s). format: 'openai'|'langchain'|'anthropic'|'all'."""
        if format == "openai":
            return {"openai": self.to_openai(skill_md_content)}
        elif format == "langchain":
            return {"langchain": self.to_langchain(skill_md_content)}
        elif format == "anthropic":
            return {"anthropic": self.to_anthropic(skill_md_content)}
        else:
            return {
                "openai": self.to_openai(skill_md_content),
                "langchain": self.to_langchain(skill_md_content),
                "anthropic": self.to_anthropic(skill_md_content),
            }

    def _parse_frontmatter(self, text: str) -> Dict[str, Any]:
        """Parse YAML frontmatter from SKILL.md."""
        if not text.startswith("---"):
            return {}
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}
        try:
            import yaml
            return yaml.safe_load(parts[1]) or {}
        except Exception:
            return {}

# ── v2.10: Agent Export Methods ──

class AgentExporter:
    """Export AGENT.md agent definitions to external framework formats."""

    def _parse_agent_frontmatter(self, content: str) -> dict:
        if not content.startswith("---"):
            return {}
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}
        import yaml
        try:
            return yaml.safe_load(parts[1]) or {}
        except Exception:
            return {}

    def to_openai_assistant(self, agent_md_content: str) -> dict:
        """Export AGENT.md → OpenAI Assistant API spec."""
        fm = self._parse_agent_frontmatter(agent_md_content)
        name = fm.get("name", "aiplat_agent")
        desc = fm.get("description", fm.get("display_name", ""))
        model = fm.get("model", "auto")

        return {
            "name": name,
            "description": desc,
            "model": model if model != "auto" else "gpt-4",
            "instructions": str(fm.get("system_prompt", ""))[:2000] or str(fm.get("config", {}).get("system_prompt", ""))[:2000],
            "tools": [{"type": "code_interpreter"}],
            "metadata": {
                "agent_type": fm.get("agent_type", "conversational"),
                "required_skills": fm.get("required_skills", []) or fm.get("skills", []),
                "version": fm.get("version", "1.0.0"),
                "source": "aiPlat AGENT.md",
            }
        }

    def to_langgraph_config(self, agent_md_content: str) -> dict:
        """Export AGENT.md → LangGraph agent configuration."""
        fm = self._parse_agent_frontmatter(agent_md_content)
        name = fm.get("name", "aiplat_agent")
        phase = fm.get("phase", "")
        return {
            "agent_name": name,
            "agent_type": fm.get("agent_type", "react"),
            "system_prompt": str(fm.get("system_prompt", ""))[:3000],
            "tools": fm.get("required_tools", []) or fm.get("tools", []),
            "skills": fm.get("required_skills", []) or fm.get("skills", []),
            "pipeline_stage": {
                "phase": phase,
                "output_artifact": fm.get("output_artifact", ""),
                "auto_hitl": fm.get("auto_hitl", False),
                "hitl_phase": fm.get("hitl_phase", ""),
            } if phase else None,
            "metadata": {"version": fm.get("version", "1.0.0"), "source": "aiPlat AGENT.md"},
        }
