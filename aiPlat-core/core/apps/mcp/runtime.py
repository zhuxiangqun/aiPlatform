"""
MCP Runtime wiring (Roadmap-2 / Roadmap-3).

Goal:
- Turn filesystem-configured MCP servers (via MCPManager) into runtime tools (ToolRegistry).
- Apply policy (allowed_tools, risk_level, tool_risk, approval_required, prod_allowed).
- Keep it best-effort and safe-by-default in production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from core.apps.mcp.client import MCPClientConfig, MCPClientManager
from core.apps.mcp.types import TransportType
from core.apps.mcp.adapter import MCPClientWrapper
from core.policy.engine import evaluate_mcp_server, PolicyDecision


@dataclass
class MCPRuntimeServerState:
    server_name: str
    tool_names: List[str]


class MCPRuntime:
    def __init__(self) -> None:
        self._manager = MCPClientManager()
        self._wrapper = MCPClientWrapper(self._manager)
        self._registered: Dict[str, MCPRuntimeServerState] = {}

    @property
    def manager(self) -> MCPClientManager:
        return self._manager

    def _is_prod(self) -> bool:
        return os.getenv("AIPLAT_ENV", "").lower() in {"prod", "production"}

    async def sync_from_servers(self, *, servers: List[Any], tool_registry: Any) -> Dict[str, Any]:
        """
        Sync runtime clients & ToolRegistry tools from a list of MCPServerInfo-like objects.

        Returns a summary:
          { "connected": [...], "skipped": [...], "unregistered": [...] }
        """
        enabled = {s.name: s for s in servers if getattr(s, "enabled", False)}
        summary = {"connected": [], "skipped": [], "unregistered": []}

        # Unregister servers removed/disabled
        for server_name in list(self._registered.keys()):
            if server_name not in enabled:
                await self._disconnect_and_unregister(server_name, tool_registry)
                summary["unregistered"].append(server_name)

        # Connect / register enabled
        for server_name, s in enabled.items():
            try:
                await self._connect_and_register(s, tool_registry)
                summary["connected"].append(server_name)
            except Exception as e:
                summary["skipped"].append({"server": server_name, "reason": str(e)})
        return summary

    async def _disconnect_and_unregister(self, server_name: str, tool_registry: Any) -> None:
        state = self._registered.get(server_name)
        if state:
            for name in state.tool_names:
                try:
                    tool_registry.unregister(name)
                except Exception:
                    pass
            self._registered.pop(server_name, None)
        try:
            await self._manager.remove_server(server_name)
        except Exception:
            pass

    def _policy(self, s: Any) -> Dict[str, Any]:
        meta = getattr(s, "metadata", None)
        if isinstance(meta, dict) and isinstance(meta.get("policy"), dict):
            return meta.get("policy") or {}
        return {}

    def _prod_allowed(self, s: Any) -> bool:
        # allow override via policy.yaml or server.yaml metadata
        pol = self._policy(s)
        if pol.get("prod_allowed") is not None:
            return bool(pol.get("prod_allowed"))
        meta = getattr(s, "metadata", None)
        if isinstance(meta, dict) and meta.get("prod_allowed") is not None:
            return bool(meta.get("prod_allowed"))
        return False

    async def _connect_and_register(self, s: Any, tool_registry: Any) -> None:
        # Production safety: forbid stdio unless explicitly allowed.
        transport = str(getattr(s, "transport", "sse") or "sse").lower()
        # PR-07: unify via policy_engine (tenant-aware best-effort)
        if True:
            try:
                from core.harness.kernel.runtime import get_kernel_runtime
                from core.harness.kernel.execution_context import get_active_request_context

                rt = get_kernel_runtime()
                store = getattr(rt, "execution_store", None) if rt else None
                ar = None
                try:
                    ar = get_active_request_context()
                except Exception:
                    ar = None
                tenant_id = getattr(ar, "tenant_id", None) if ar else None
                actor_id = getattr(ar, "actor_id", None) if ar else None
                actor_role = getattr(ar, "actor_role", None) if ar else None

                meta = getattr(s, "metadata", None)
                ev = await evaluate_mcp_server(
                    store=store,
                    tenant_id=str(tenant_id) if tenant_id else None,
                    actor_id=str(actor_id) if actor_id else None,
                    actor_role=str(actor_role) if actor_role else None,
                    server_name=str(getattr(s, "name", "")),
                    transport=str(transport),
                    server_metadata=meta if isinstance(meta, dict) else None,
                )
                if ev.decision == PolicyDecision.DENY:
                    try:
                        if store is not None:
                            await store.add_syscall_event(
                                {
                                    "kind": "mcp",
                                    "name": str(getattr(s, "name", "")),
                                    "status": "policy_denied",
                                    "error": ev.reason,
                                    "error_code": ev.reason_code,
                                    "tenant_id": ev.tenant_id,
                                    "args": {"transport": str(transport), "policy_version": ev.policy_version},
                                }
                            )
                    except Exception:
                        pass
                    raise RuntimeError(ev.reason)
            except Exception:
                # fallback to legacy prod guard
                if self._is_prod() and transport == "stdio" and not self._prod_allowed(s):
                    # Record an audit event (best-effort) so operators can see why tools are missing.
                    try:
                        from core.harness.kernel.runtime import get_kernel_runtime
 
                        rt = get_kernel_runtime()
                        store = getattr(rt, "execution_store", None) if rt else None
                        if store is not None:
                            await store.add_syscall_event(
                                {
                                    "kind": "mcp",
                                    "name": str(getattr(s, "name", "")),
                                    "status": "prod_denied",
                                    "error": "prod policy denies stdio MCP server",
                                    "error_code": "PROD_DENIED",
                                    "args": {"transport": "stdio"},
                                }
                            )
                    except Exception:
                        pass
                    raise RuntimeError("prod policy denies stdio MCP server (set policy.prod_allowed=true to allow)")

        cfg = self._to_client_config(s)
        # add_server connects + lists tools
        await self._manager.add_server(cfg.name, cfg)

        pol = self._policy(s)
        risk_level = str(pol.get("risk_level") or ("high" if transport == "stdio" else "medium"))
        tool_risk = pol.get("tool_risk") if isinstance(pol.get("tool_risk"), dict) else {}
        approval_required = pol.get("approval_required")
        allowed_tools = getattr(s, "allowed_tools", None) or []

        # Register tools; names are mcp.<server>.<tool>
        before = set(tool_registry.list_tools())
        await self._wrapper.register_server_tools(
            cfg.name,
            tool_registry,
            allowed_tools=allowed_tools,
            risk_level=risk_level,
            tool_risk=tool_risk,
            approval_required=approval_required if approval_required is not None else None,
        )
        after = set(tool_registry.list_tools())
        added = sorted(list(after - before))
        self._registered[cfg.name] = MCPRuntimeServerState(server_name=cfg.name, tool_names=added)

    def _to_client_config(self, s: Any) -> MCPClientConfig:
        transport = str(getattr(s, "transport", "sse") or "sse").lower()
        if transport not in {"sse", "http", "stdio"}:
            transport = "sse"

        t = TransportType.SSE
        if transport == "http":
            t = TransportType.HTTP
        elif transport == "stdio":
            t = TransportType.STDIO

        return MCPClientConfig(
            name=str(getattr(s, "name")),
            transport=t,
            url=getattr(s, "url", None),
            command=getattr(s, "command", None),
            args=list(getattr(s, "args", None) or []),
            timeout=30000,
        )
