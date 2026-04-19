from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PluginManifest:
    """
    PR-11: workflow/plugin manifest (MVP)

    - required_tools: 插件声明的最小工具集（用于 policy/审计/审批）
    - commands: 预留（后续可对接 commands+agents+hooks）
    """

    plugin_id: str
    name: str
    version: str
    description: str = ""
    # P0: plugin standardization
    dependencies: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    permissions: Dict[str, Any] = field(default_factory=dict)  # declared capabilities (tools/mcp/files/network/etc.)
    tests: List[Dict[str, Any]] = field(default_factory=list)  # test declarations (pytest/autosmoke/command)
    risk_level: Optional[str] = None
    risk_weight: Optional[float] = None
    commands: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PluginManifest":
        if not isinstance(d, dict):
            raise ValueError("manifest must be object")
        pid = str(d.get("plugin_id") or d.get("id") or "").strip()
        if not pid:
            raise ValueError("manifest.plugin_id required")
        name = str(d.get("name") or pid).strip()
        version = str(d.get("version") or "0.0.0").strip()
        deps = d.get("dependencies") if isinstance(d.get("dependencies"), list) else []
        deps = [str(x) for x in deps if isinstance(x, (str, int, float)) and str(x).strip()]
        required_tools = d.get("required_tools") if isinstance(d.get("required_tools"), list) else []
        required_tools = [str(x) for x in required_tools if isinstance(x, (str, int, float)) and str(x).strip()]
        permissions = d.get("permissions") if isinstance(d.get("permissions"), dict) else {}
        tests = d.get("tests") if isinstance(d.get("tests"), list) else []
        return cls(
            plugin_id=pid,
            name=name,
            version=version,
            description=str(d.get("description") or ""),
            dependencies=deps,
            required_tools=required_tools,
            permissions=permissions,
            tests=tests,
            risk_level=str(d.get("risk_level")) if d.get("risk_level") is not None else None,
            risk_weight=float(d.get("risk_weight")) if d.get("risk_weight") is not None else None,
            commands=d.get("commands") if isinstance(d.get("commands"), list) else [],
            metadata=d.get("metadata") if isinstance(d.get("metadata"), dict) else {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "dependencies": list(self.dependencies or []),
            "required_tools": list(self.required_tools or []),
            "permissions": dict(self.permissions or {}),
            "tests": list(self.tests or []),
            "risk_level": self.risk_level,
            "risk_weight": self.risk_weight,
            "commands": list(self.commands or []),
            "metadata": dict(self.metadata or {}),
        }
