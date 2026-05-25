"""
agentskills.io → aiPlatform SKILL.md converter.

Converts the agentskills.io open standard format to aiPlatform's frontmatter + SOP SKILL.md format.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _parse_agentskills_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from agentskills.io SKILL.md."""
    text = text or ""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1].strip()
    body = parts[2].strip()
    fm: Dict[str, Any] = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip().strip("'\"")
        if not key:
            continue
        # Handle nested metadata
        if key == "metadata" and val == "":
            continue
        fm[key] = val
    return fm, body


def _extract_headings(body: str) -> List[Tuple[str, str]]:
    """Extract markdown heading sections from body."""
    sections: List[Tuple[str, str]] = []
    current_title = ""
    current_content: List[str] = []
    for line in body.split("\n"):
        if line.startswith("#"):
            if current_title:
                sections.append((current_title, "\n".join(current_content).strip()))
            current_title = line.lstrip("#").strip()
            current_content = []
        else:
            current_content.append(line)
    if current_title:
        sections.append((current_title, "\n".join(current_content).strip()))
    return sections


_INPUT_HINTS = {
    "code": {"code": {"type": "string", "description": "Source code to process", "required": True}},
    "text": {"text": {"type": "string", "description": "Input text", "required": True}},
    "file": {"file_path": {"type": "string", "description": "Path to input file", "required": True}},
    "query": {"query": {"type": "string", "description": "Search query or question", "required": True}},
    "image": {"image": {"type": "string", "description": "Image URL or file path", "required": True}},
    "data": {"data": {"type": "object", "description": "Input data to process", "required": True}},
    "url": {"url": {"type": "string", "description": "URL to process", "required": True}},
}

_OUTPUT_HINTS = {
    "code": {"result": {"type": "string", "description": "Processed result", "required": True}},
    "text": {"result": {"type": "string", "description": "Processed result", "required": True}},
    "file": {"result": {"type": "string", "description": "Result summary", "required": True}},
    "query": {"result": {"type": "string", "description": "Query result", "required": True}},
    "image": {"result": {"type": "string", "description": "Analysis result", "required": True}},
    "data": {"result": {"type": "object", "description": "Processed result", "required": True}},
    "url": {"result": {"type": "string", "description": "Fetch result", "required": True}},
}

_CATEGORY_HINTS = {
    "code": "code",
    "review": "code",
    "text": "text",
    "doc": "document",
    "pdf": "document",
    "data": "analysis",
    "analysis": "analysis",
    "image": "media",
    "video": "media",
    "search": "retrieval",
    "query": "retrieval",
    "translate": "text",
}


def _guess_category(name: str, description: str) -> str:
    lower = (name + " " + description).lower()
    for hint, cat in _CATEGORY_HINTS.items():
        if hint in lower:
            return cat
    return "general"


def _guess_io_schema(name: str, description: str, body: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    lower = (name + " " + description + " " + body).lower()
    for hint, schema in _INPUT_HINTS.items():
        if hint in lower:
            return schema, _OUTPUT_HINTS.get(hint, {"result": {"type": "string", "required": True}})
    return (
        {"input": {"type": "string", "description": "Input to process", "required": True}},
        {"result": {"type": "string", "description": "Processed result", "required": True}},
    )


def convert_agentskills_to_aiplat(raw_md: str, skill_dir_name: str = "") -> str:
    """Convert an agentskills.io SKILL.md to aiPlatform format."""
    fm, body = _parse_agentskills_frontmatter(raw_md)
    if not fm:
        return raw_md  # already converted or invalid

    fm_name = str(fm.get("name") or skill_dir_name or "unknown")
    fm_desc = str(fm.get("description") or fm_name)
    category = _guess_category(fm_name, fm_desc)
    input_schema, output_schema = _guess_io_schema(fm_name, fm_desc, body)

    # Build aiPlatform frontmatter
    import json as _json
    lines = [
        "---",
        f"name: {fm_name}",
        f"display_name: {fm_name.replace('-', ' ').title()}",
        f"description: {fm_desc[:1024]}",
        f"category: {category}",
        "version: 0.1.0",
        "status: draft",
        "execution_mode: prompt",
    ]
    # Carry over agentskills.io optional fields
    if fm.get("license"):
        lines.append(f"license: {fm.get('license')}")
    if fm.get("compatibility"):
        lines.append(f"compatibility: {fm.get('compatibility')}")
    # Add permissions
    lines.append("permissions: []")
    lines.append("effects:")
    lines.append("  - type: read")
    lines.append("    resources: [filesystem:~/.aiplat]")
    lines.append("    idempotent: true")
    lines.append("    rollback_available: false")

    # Add schemas
    lines.append(f"input_schema: {_json.dumps(input_schema, ensure_ascii=False)}")
    lines.append(f"output_schema: {_json.dumps(output_schema, ensure_ascii=False)}")
    lines.append("---")

    # Add SOP body
    if body.strip():
        lines.append("")
        lines.append("## SOP")
        lines.append(body.strip())

    return "\n".join(lines) + "\n"


def is_agentskills_format(raw_md: str) -> bool:
    """Detect if SKILL.md is in agentskills.io format (YAML frontmatter with name+description only, no aiPlatform fields)."""
    try:
        fm, _ = _parse_agentskills_frontmatter(raw_md)
        if not fm:
            return False
        has_name = bool(fm.get("name"))
        has_description = bool(fm.get("description"))
        has_aiplat_schema = bool(fm.get("input_schema") or fm.get("output_schema") or fm.get("execution_mode") or fm.get("category"))
        # If it has agentskills fields AND missing aiPlatform-specific fields, it's agentskills format
        return has_name and has_description and not has_aiplat_schema
    except Exception:
        return False


def convert_hermes_so_ul_to_agent_md(soul_md: str, agents_md: str = "", agent_name: str = "hermes_agent") -> str:
    """Convert Hermes SOUL.md (+ optional AGENTS.md) into aiPlatform AGENT.md."""
    body_parts = []
    if soul_md.strip():
        body_parts.append("## Personality (from Hermes SOUL.md)")
        body_parts.append(soul_md.strip())
    if agents_md.strip():
        body_parts.append("## Project Rules (from Hermes AGENTS.md)")
        body_parts.append(agents_md.strip())

    safe_name = re.sub(r"[^a-z0-9_]", "_", agent_name.lower())[:32]
    lines = [
        "---",
        f"name: {safe_name}",
        f"display_name: {agent_name}",
        "description: Imported from Hermes Agent",
        "agent_type: conversational",
        "version: 0.1.0",
        "status: draft",
        "category: general",
        "tags: [hermes, imported]",
        "skills: []",
        "tools: []",
        "model: auto",
        "---",
        "",
        "\n\n".join(body_parts),
    ]
    return "\n".join(lines) + "\n"


def convert_mcp_json_to_server_yaml(mcp_json_path: str) -> List[Dict[str, str]]:
    """Convert Hermes MCP config JSON files to aiPlatform server.yaml + policy.yaml."""
    import json as _json
    results: List[Dict[str, str]] = []
    try:
        data = _json.loads(Path(mcp_json_path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return results

    servers = data.get("mcpServers") or data.get("servers") or {}
    for srv_name, srv_cfg in servers.items():
        if not isinstance(srv_cfg, dict):
            continue
        cmd = str(srv_cfg.get("command") or "")
        args = srv_cfg.get("args") if isinstance(srv_cfg.get("args"), list) else []
        env = srv_cfg.get("env") if isinstance(srv_cfg.get("env"), dict) else {}
        url = str(srv_cfg.get("url") or "")

        server_lines = [
            f"name: {srv_name}",
            "enabled: true",
        ]
        if url:
            server_lines.append(f"transport: sse")
            server_lines.append(f"url: {url}")
        elif cmd:
            server_lines.append("transport: stdio")
            server_lines.append(f"command: {cmd}")
            if args:
                import json as _j2
                server_lines.append(f"args: {_j2.dumps(args)}")
        if env:
            import json as _j3
            server_lines.append(f"env: {_j3.dumps(env)}")
        server_lines.append("metadata:")
        server_lines.append("  description: \"Imported from Hermes MCP config\"")

        results.append({
            "name": srv_name,
            "server": "\n".join(server_lines) + "\n",
            "policy": f"allowed_tools: []\nrisk_level: low\napproval_required: false\n",
        })
    return results


__all__ = [
    "convert_agentskills_to_aiplat",
    "is_agentskills_format",
    "convert_hermes_so_ul_to_agent_md",
    "convert_mcp_json_to_server_yaml",
]
