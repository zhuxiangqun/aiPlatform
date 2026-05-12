"""
Plugin manifest validator (platform-side).

Runs BEFORE a plugin is forwarded to core's /api/core/plugins.
Defense-in-depth: catches manifest issues at the platform boundary
so core never sees invalid registrations.

Validates:
  - Required fields (name, version)
  - Entry point declarations (skills / tools / mcp_servers)
  - Skill effects completeness (§5.19)
  - Tool schema completeness
  - MCP server URL validity
  - High-risk plugin permission declarations
"""

from __future__ import annotations

from typing import Any, Dict, List


def validate_plugin_manifest(manifest: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    name = str(manifest.get("name", "")).strip()
    if not name:
        errors.append("name is required")
    version = str(manifest.get("version", "")).strip()
    if not version:
        errors.append("version is required")

    skills = list(manifest.get("skills", []) or [])
    tools = list(manifest.get("tools", []) or [])
    mcp_servers = list(manifest.get("mcp_servers", []) or [])
    if not skills and not tools and not mcp_servers:
        errors.append("at least one of skills / tools / mcp_servers is required")

    for sk in skills:
        sk_name = str(sk.get("name", "") or "?")
        effects = list(sk.get("effects", []) or [])
        if not effects:
            errors.append(f"skill '{sk_name}': effects declaration required (§5.19)")
            continue
        for e in effects:
            if "type" not in e:
                errors.append(f"skill '{sk_name}': effects[].type required")
            if "idempotent" not in e:
                errors.append(f"skill '{sk_name}': effects[].idempotent required")
        has_write = any(e.get("type") in ("write", "execute", "both") for e in effects)
        if has_write and bool(sk.get("idempotent", True)):
            errors.append(
                f"skill '{sk_name}': has write/execute effects but idempotent=true. "
                f"Set idempotent=false or remove write effects."
            )
        for e in effects:
            e_type = str(e.get("type") or "")
            if e_type in ("write", "execute", "both") and not bool(e.get("rollback_available")):
                errors.append(
                    f"skill '{sk_name}': effects[].type={e_type} requires rollback_available=true"
                )

    for t in tools:
        t_name = str(t.get("name", "") or "?")
        if not t_name:
            errors.append("tool name is required")
            continue
        if not t.get("input_schema"):
            errors.append(f"tool '{t_name}': input_schema required")

    for mcp in mcp_servers:
        mcp_name = str(mcp.get("name", "") or "?")
        url = str(mcp.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            errors.append(
                f"mcp_server '{mcp_name}': invalid URL '{url[:80]}'. "
                f"Must start with http:// or https://"
            )

    risk = str(manifest.get("risk_level", "low"))
    perms = list(manifest.get("permissions", []) or [])
    if risk in ("high", "critical") and not perms:
        errors.append(
            f"plugin '{name}': risk_level={risk} requires explicit permissions declaration"
        )

    return errors
