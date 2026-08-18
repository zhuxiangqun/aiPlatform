"""Profile — resource isolation boundary (A2.4 A2-axis L3→L4 enabler).

Bundles a MemoryManager namespace + skills workspace subdirectory + MCP server
list under a named profile, enabling per-team/per-project isolation without
full multi-tenant overhead.

MemoryManager namespace isolation already exists (manager.py:113 namespace param).
This module provides the declarative config layer to wire the three resource types
together under one profile name.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.profile")


@dataclass
class ProfileConfig:
    """Minimal resource-isolation profile.

    Loaded from ~/.aiplat/profiles/{name}.yaml by ProfileManager.
    Each profile gets its own MemoryManager namespace, skills workspace,
    and (future) MCP server list."""

    name: str
    description: str = ""
    namespace: str = ""
    skills_dir: str = ""
    mcp_servers: List[str] = field(default_factory=list)
    default: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    profile_type: str = "customer"  # "customer" | "template"

    @classmethod
    def from_yaml(cls, path: str) -> Optional["ProfileConfig"]:
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            if not data.get("name"):
                return None
            md = data.get("metadata", {}) or {}
            if "deployment_mode" in data and "deployment_mode" not in md:
                md["deployment_mode"] = data["deployment_mode"]
            if "industry" in data and "industry" not in md:
                md["industry"] = data["industry"]
            return cls(
                name=data["name"],
                description=data.get("description", ""),
                namespace=data.get("namespace", data["name"]),
                skills_dir=data.get("skills_dir", f"profiles/{data['name']}/skills"),
                mcp_servers=data.get("mcp_servers", []),
                default=data.get("default", False),
                metadata=md,
                profile_type=data.get("profile_type", "customer"),
            )
        except Exception:
            return None


class ProfileManager:
    """Scans ~/.aiplat/profiles/*.yaml and provides profile lookup.

    Usage:
        pm = ProfileManager()
        profile = pm.get("ops")  # → ProfileConfig
        mm = get_memory_manager(namespace=profile.namespace)
    """

    def __init__(self, home_dir: str = ""):
        h = home_dir or os.path.expanduser(os.environ.get("AIPLAT_HOME", "~/.aiplat"))
        self._profiles_dir = os.path.join(h, "profiles")
        self._profiles: Dict[str, ProfileConfig] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        if not os.path.isdir(self._profiles_dir):
            return
        for entry in sorted(os.listdir(self._profiles_dir)):
            if not entry.endswith(".yaml") or entry == ".registry.yaml":
                continue
            fp = os.path.join(self._profiles_dir, entry)
            cfg = ProfileConfig.from_yaml(fp)
            if cfg:
                self._profiles[cfg.name] = cfg

    def get(self, name: str) -> Optional[ProfileConfig]:
        self._ensure_loaded()
        return self._profiles.get(name)

    def get_default(self) -> ProfileConfig:
        self._ensure_loaded()
        for cfg in self._profiles.values():
            if cfg.default:
                return cfg
        return ProfileConfig(name="default", namespace="default",
                             description="Implicit default profile")

    def get_mcp_servers(self, name: str) -> List[str]:
        """Return MCP server IDs scoped to a profile (per-profile MCP isolation, A2.4 L3→L4).
        Falls back to all registered servers if profile has no explicit mcp_servers list."""
        cfg = self.get(name)
        if cfg and cfg.mcp_servers:
            return cfg.mcp_servers
        # backward compat: empty list = all servers
        try:
            from core.harness.integration import get_mcp_client_manager  # P0-A1: DI 解析
            return get_mcp_client_manager().list_servers()
        except Exception:
            return []

    def list_all(self) -> List[ProfileConfig]:
        self._ensure_loaded()
        return list(self._profiles.values())

    def create(self, name: str, namespace: str = "", description: str = "",
               industry: str = "", deployment_mode: str = "online",
               profile_type: str = "customer") -> ProfileConfig:
        """Create a new profile and persist to ~/.aiplat/profiles/{namespace}.yaml."""
        import yaml
        ns = namespace or name.lower().replace(" ", "-")
        os.makedirs(self._profiles_dir, exist_ok=True)
        fp = os.path.join(self._profiles_dir, f"{ns}.yaml")
        data = {
            "name": name,
            "namespace": ns,
            "description": description or name,
            "industry": industry,
            "deployment_mode": deployment_mode,
            "profile_type": profile_type,
            "mcp_servers": [],
            "default": False,
        }
        with open(fp, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        cfg = ProfileConfig(
            name=name, namespace=ns,
            description=description or name,
            default=False, mcp_servers=[],
            metadata={"industry": industry, "deployment_mode": deployment_mode},
            profile_type=profile_type,
        )
        self._profiles[cfg.name] = cfg
        self._profiles[ns] = cfg
        return cfg

    def delete(self, namespace: str) -> bool:
        """Delete a profile YAML file and remove from cache."""
        fp = os.path.join(self._profiles_dir, f"{namespace}.yaml")
        if os.path.isfile(fp):
            try:
                os.remove(fp)
                self._profiles.pop(namespace, None)
                self._loaded = False
                self._ensure_loaded()
                return True
            except OSError:
                return False
        return False

    def update(self, namespace: str, name: str = "", description: str = "",
               deployment_mode: str = "", industry: str = "") -> Optional[ProfileConfig]:
        """Update an existing profile's fields and rewrite YAML."""
        fp = os.path.join(self._profiles_dir, f"{namespace}.yaml")
        cfg = self.get(namespace)
        if not cfg or not os.path.isfile(fp):
            # Try by name
            for c in self.list_all():
                if c.name == namespace:
                    cfg = c
                    fp = os.path.join(self._profiles_dir, f"{c.namespace}.yaml")
                    break
            if not cfg:
                return None
        import yaml
        with open(fp, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if name: data["name"] = name
        if description: data["description"] = description
        if deployment_mode: data["deployment_mode"] = deployment_mode
        if industry: data["industry"] = industry
        with open(fp, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        self._loaded = False
        self._ensure_loaded()
        return self.get(cfg.namespace)
        return False


# Singleton
_profile_manager: Optional[ProfileManager] = None


def get_profile_manager() -> ProfileManager:
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ProfileManager()
    return _profile_manager
