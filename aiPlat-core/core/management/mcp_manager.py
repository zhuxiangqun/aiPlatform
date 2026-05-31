"""
MCP Manager - directory-based MCP server configuration.

Goal:
- Provide a filesystem-backed source of truth for MCP server configs.
- Support multi-path loading: ~/.aiplat/mcps + <repo>/mcps (repo overrides global).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import yaml


@dataclass
class MCPServerInfo:
    name: str
    enabled: bool = True
    status: str = "draft"  # draft | ready | published | listed | deprecated
    transport: str = "sse"  # sse|stdio|http etc
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    auth: Optional[Dict[str, Any]] = None
    allowed_tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MCPManager:
    def __init__(self, *, scope: str = "engine", reserved_names: Optional[set] = None):
        self._servers: Dict[str, MCPServerInfo] = {}
        self._scope = scope  # "engine" | "workspace"
        self._reserved_names = reserved_names or set()
        self.reload()

    def _resolve_mcp_paths(self) -> List[Path]:
        repo_root = Path(__file__).resolve().parents[2]  # aiPlat-core/
        engine_default = repo_root / "core" / "engine" / "mcps"
        workspace_default = Path.home() / ".aiplat" / "mcps"

        scope = (self._scope or "engine").strip().lower()
        if scope not in {"engine", "workspace"}:
            scope = "engine"

        paths_env = os.environ.get(f"AIPLAT_{scope.upper()}_MCPS_PATHS")
        if paths_env:
            parts = [p.strip() for p in paths_env.split(os.pathsep) if p.strip()]
            return [Path(p).expanduser().resolve() for p in parts]

        single = os.environ.get(f"AIPLAT_{scope.upper()}_MCPS_PATH")
        if single:
            return [Path(single).expanduser().resolve()]

        return [engine_default.resolve()] if scope == "engine" else [workspace_default.resolve()]

    def _resolve_mcp_base_path(self) -> Path:
        paths = self._resolve_mcp_paths()
        return paths[-1] if paths else (Path(__file__).resolve().parents[2] / "mcps")

    def _find_server_dir(self, name: str) -> Optional[Path]:
        for base in reversed(self._resolve_mcp_paths()):
            p = base / name
            if p.exists() and p.is_dir():
                return p
        return None

    def reload(self) -> None:
        """Reload from filesystem."""
        self._servers = {}
        now = datetime.now(timezone.utc)
        for base in self._resolve_mcp_paths():
            if not base.exists():
                continue
            for item in base.iterdir():
                if not item.is_dir() or item.name.startswith("."):
                    continue
                server_yaml = item / "server.yaml"
                if not server_yaml.exists():
                    continue
                try:
                    data = yaml.safe_load(server_yaml.read_text(encoding="utf-8")) or {}
                except Exception:
                    data = {}
                if not isinstance(data, dict):
                    data = {}

                name = str(data.get("name") or item.name)
                enabled = bool(data.get("enabled", True))
                status = str(data.get("status") or "draft")
                transport = str(data.get("transport") or "sse")
                url = data.get("url")
                command = data.get("command")
                args = data.get("args") or []
                if not isinstance(args, list):
                    args = []
                auth = data.get("auth") if isinstance(data.get("auth"), dict) else None

                # optional policy
                allowed_tools: List[str] = []
                policy_meta: Dict[str, Any] = {}
                policy_yaml = item / "policy.yaml"
                if policy_yaml.exists():
                    try:
                        pol = yaml.safe_load(policy_yaml.read_text(encoding="utf-8")) or {}
                        if isinstance(pol, dict) and isinstance(pol.get("allowed_tools"), list):
                            allowed_tools = [str(x) for x in pol.get("allowed_tools") if str(x).strip()]
                        # extended fields (Roadmap-2): risk_level / tool_risk / approval_required / prod_allowed
                        if isinstance(pol, dict):
                            if pol.get("risk_level") is not None:
                                policy_meta["risk_level"] = str(pol.get("risk_level"))
                            if isinstance(pol.get("tool_risk"), dict):
                                policy_meta["tool_risk"] = {str(k): str(v) for k, v in (pol.get("tool_risk") or {}).items()}
                            if pol.get("approval_required") is not None:
                                policy_meta["approval_required"] = bool(pol.get("approval_required"))
                            if pol.get("prod_allowed") is not None:
                                policy_meta["prod_allowed"] = bool(pol.get("prod_allowed"))
                    except Exception:
                        allowed_tools = []
                        policy_meta = {}

                meta = dict(data.get("metadata") or {}) if isinstance(data.get("metadata"), dict) else {}
                if policy_meta:
                    meta.setdefault("policy", {})
                    if isinstance(meta.get("policy"), dict):
                        meta["policy"].update(policy_meta)
                meta.setdefault("filesystem", {})
                if isinstance(meta["filesystem"], dict):
                    meta["filesystem"]["server_dir"] = str(item)
                    meta["filesystem"]["server_yaml"] = str(server_yaml)
                    meta["filesystem"]["policy_yaml"] = str(policy_yaml) if policy_yaml.exists() else None
                    meta["filesystem"]["source"] = str(base)

                self._servers[name] = MCPServerInfo(
                    name=name,
                    enabled=enabled,
                    status=status,
                    transport=transport,
                    url=url,
                    command=command,
                    args=list(args),
                    auth=auth,
                    allowed_tools=allowed_tools,
                    metadata=meta,
                    created_at=now,
                    updated_at=now,
                )

    def list_servers(self) -> List[MCPServerInfo]:
        return list(self._servers.values())

    def get_server_names(self) -> List[str]:
        return list(self._servers.keys())

    def get_server(self, name: str) -> Optional[MCPServerInfo]:
        return self._servers.get(name)

    def upsert_server(self, info: MCPServerInfo) -> MCPServerInfo:
        """Write to primary path and reload."""
        if self._reserved_names and info.name in self._reserved_names:
            raise ValueError(f"MCP server '{info.name}' is reserved by engine scope and cannot be created/updated in workspace.")
        base = self._resolve_mcp_base_path()
        server_dir = base / info.name
        server_dir.mkdir(parents=True, exist_ok=True)
        server_yaml = server_dir / "server.yaml"
        policy_yaml = server_dir / "policy.yaml"

        data = {
            "name": info.name,
            "enabled": bool(info.enabled),
            "status": info.status or "draft",
            "transport": info.transport,
            "url": info.url,
            "command": info.command,
            "args": info.args or [],
            "auth": info.auth,
            "metadata": {k: v for k, v in (info.metadata or {}).items() if k != "filesystem"},
        }
        server_yaml.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        pol = {"allowed_tools": info.allowed_tools or []}
        # persist optional policy extensions if present
        policy_extra = info.metadata.get("policy") if isinstance(info.metadata, dict) else None
        if isinstance(policy_extra, dict):
            for k in ("risk_level", "tool_risk", "approval_required", "prod_allowed"):
                if k in policy_extra and policy_extra.get(k) is not None:
                    pol[k] = policy_extra.get(k)
        policy_yaml.write_text(yaml.safe_dump(pol, sort_keys=False, allow_unicode=True), encoding="utf-8")

        self.reload()
        return self._servers[info.name]

    def set_enabled(self, name: str, enabled: bool) -> bool:
        info = self._servers.get(name)
        if not info:
            return False
        info.enabled = enabled
        self.upsert_server(info)
        return True

    def delete_server(self, name: str) -> bool:
        """Delete a server from disk and in-memory."""
        server_dir = self._find_server_dir(name)
        if server_dir:
            import shutil as _shutil
            _shutil.rmtree(server_dir, ignore_errors=True)
        self._servers.pop(name, None)
        return True

    # ── Installer methods (workspace scope only) ────────────────────────

    async def installer_install(self, *, source_type: str, url: Optional[str] = None,
                                ref: Optional[str] = None, path: Optional[str] = None,
                                mcp_id: Optional[str] = None, subdir: Optional[str] = None,
                                auto_detect_subdir: bool = True, allow_overwrite: bool = False,
                                metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if (self._scope or "engine").strip().lower() != "workspace":
            raise PermissionError("installer_install_only_allowed_in_workspace_scope")
        from core.management.asset_installer import MCPInstaller
        base = self._resolve_mcp_base_path()
        base.mkdir(parents=True, exist_ok=True)
        inst = MCPInstaller(target_base_dir=base)
        st = str(source_type or "").strip().lower()
        if st == "git":
            res = inst.install_from_git(url=str(url or ""), ref=str(ref or ""),
                asset_id=mcp_id, subdir=subdir, auto_detect_subdir=bool(auto_detect_subdir),
                allow_overwrite=bool(allow_overwrite), metadata=metadata)
        elif st == "path":
            res = inst.install_from_path(path=str(path or ""), asset_id=mcp_id,
                subdir=subdir, auto_detect_subdir=bool(auto_detect_subdir),
                allow_overwrite=bool(allow_overwrite), metadata=metadata)
        elif st == "zip":
            res = inst.install_from_zip(zip_path=str(path or ""), asset_id=mcp_id,
                subdir=subdir, auto_detect_subdir=bool(auto_detect_subdir),
                allow_overwrite=bool(allow_overwrite), metadata=metadata)
        else:
            raise ValueError("invalid_source_type")
        self.reload()
        return {"installed": res.installed, "skipped": res.skipped, "base": str(base)}

    async def installer_plan(self, *, source_type: str, url: Optional[str] = None,
                             ref: Optional[str] = None, path: Optional[str] = None,
                             mcp_id: Optional[str] = None, subdir: Optional[str] = None,
                             auto_detect_subdir: bool = True,
                             metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if (self._scope or "engine").strip().lower() != "workspace":
            raise PermissionError("installer_plan_only_allowed_in_workspace_scope")
        from core.management.asset_installer import MCPInstaller
        base = self._resolve_mcp_base_path()
        inst = MCPInstaller(target_base_dir=base)
        st = str(source_type or "").strip().lower()
        if st == "git":
            plan = inst.plan_from_git(url=str(url or ""), ref=str(ref or ""),
                asset_id=mcp_id, subdir=subdir, auto_detect_subdir=bool(auto_detect_subdir),
                metadata=metadata)
        elif st == "path":
            plan = inst.plan_from_path(path=str(path or ""), asset_id=mcp_id,
                subdir=subdir, auto_detect_subdir=bool(auto_detect_subdir), metadata=metadata)
        elif st == "zip":
            plan = inst.plan_from_zip(zip_path=str(path or ""), asset_id=mcp_id,
                subdir=subdir, auto_detect_subdir=bool(auto_detect_subdir), metadata=metadata)
        else:
            raise ValueError("invalid_source_type")
        return {"source": plan.source, "detected_subdir": plan.detected_subdir,
                "mcps": plan.assets, "warnings": plan.warnings,
                "claude_plugin": plan.claude_plugin}

    async def installer_resolve_head(self, *, url: str) -> Dict[str, Any]:
        from core.management.asset_installer import resolve_remote_head_sha
        return {"url": url, "sha": resolve_remote_head_sha(url)}
