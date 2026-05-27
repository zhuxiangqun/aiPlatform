"""
MCP server configuration validator — checks server.yaml compliance.

Checks:
  1. YAML syntax validity
  2. Required fields (name, transport)
  3. Transport validity (sse/stdio/http)
  4. URL format (for sse/http transport)
  5. Recommended: allowed_tools not empty
"""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ConfigIssue:
    server: str
    file: str
    severity: str  # "error" | "warn"
    message: str


REQUIRED_FIELDS = ["name", "transport"]
VALID_TRANSPORTS = {"sse", "stdio", "http", "streamable_http"}


def validate_mcp_server(server_yaml_path: Path) -> List[ConfigIssue]:
    """Validate a single server.yaml file. Returns list of issues."""
    issues: List[ConfigIssue] = []
    server_name = server_yaml_path.parent.name if server_yaml_path.parent.name else "unknown"
    file_path = str(server_yaml_path)

    # 1) Read file
    try:
        raw = server_yaml_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [ConfigIssue(server=server_name, file=file_path, severity="error",
                           message=f"Cannot read file: {e}")]

    # 2) YAML syntax
    import yaml
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        return [ConfigIssue(server=server_name, file=file_path, severity="error",
                           message=f"YAML parse error: {e}")]

    if not isinstance(data, dict):
        return [ConfigIssue(server=server_name, file=file_path, severity="error",
                           message="server.yaml must be a YAML mapping")]

    # 3) Required fields
    for field in REQUIRED_FIELDS:
        val = data.get(field)
        if not val or (isinstance(val, str) and not val.strip()):
            issues.append(ConfigIssue(
                server=server_name, file=file_path, severity="error",
                message=f"Missing required field: {field}"
            ))

    # 4) Transport validity
    transport = str(data.get("transport", "")).lower().strip()
    if transport and transport not in VALID_TRANSPORTS:
        issues.append(ConfigIssue(
            server=server_name, file=file_path, severity="warn",
            message=f"Unknown transport '{transport}', expected one of: {', '.join(sorted(VALID_TRANSPORTS))}"
        ))

    # 5) URL check for SSE/HTTP
    if transport in ("sse", "http", "streamable_http"):
        url = str(data.get("url", "")).strip()
        if not url:
            issues.append(ConfigIssue(
                server=server_name, file=file_path, severity="error",
                message=f"Missing url for {transport} transport"
            ))
        elif not re.match(r'^https?://', url):
            issues.append(ConfigIssue(
                server=server_name, file=file_path, severity="warn",
                message=f"URL should start with http:// or https://"
            ))

    # 6) stdio requires command
    if transport == "stdio":
        cmd = str(data.get("command", "")).strip()
        if not cmd:
            issues.append(ConfigIssue(
                server=server_name, file=file_path, severity="error",
                message="stdio transport requires 'command' field"
            ))

    # 7) Recommended: allowed_tools
    allowed = data.get("allowed_tools", [])
    if isinstance(allowed, list) and len(allowed) == 0:
        issues.append(ConfigIssue(
            server=server_name, file=file_path, severity="warn",
            message="allowed_tools is empty — no tools will be exposed"
        ))

    # 8) Recommended: display_name/description
    if not data.get("display_name") and not data.get("description"):
        issues.append(ConfigIssue(
            server=server_name, file=file_path, severity="warn",
            message="Missing display_name or description"
        ))

    return issues


def validate_all_mcp_servers(mcps_dir: str) -> tuple:
    """Validate all server.yaml files recursively. Returns (errors, warnings)."""
    errors: List[ConfigIssue] = []
    warnings: List[ConfigIssue] = []
    base = Path(mcps_dir)
    if not base.exists():
        return errors, warnings

    for yaml_path in sorted(base.rglob("server.yaml")):
        if "__pycache__" in str(yaml_path):
            continue
        issues = validate_mcp_server(yaml_path)
        for issue in issues:
            if issue.severity == "error":
                errors.append(issue)
            else:
                warnings.append(issue)

    return errors, warnings
