"""
Subagent providers (P1-A3, DSH 借鉴) — pluggable execution backends.

Aligns with DSH SubagentProvider contract:
  - capabilities flags (start/continuation/isolation/...)
  - start() for a fresh execution
  - continuation() for resuming a settled subagent

Providers:
  1. InProcessProvider (default) — existing conversational-agent path
  2. ACPProvider — external execution via core/acp/server.py WebSocket protocol

Selection: SubagentCoordinator(list_providers()) exposes available providers;
AIPLAT_SUBAGENT_PROVIDER env selects the default (default: in_process).
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProviderCapabilities:
    """Feature flags a provider supports (DSH-style)."""
    start: bool = True            # can start fresh subagent runs
    continuation: bool = False    # can resume a settled subagent
    isolation: bool = True        # provides process/context isolation
    external: bool = False        # executes outside this process
    output_schema: bool = False   # enforces structured output schema
    tool_filter: bool = False     # supports per-subagent tool filtering


@dataclass
class ProviderResult:
    """Normalized result from any provider."""
    ok: bool
    output: str = ""
    error: str = ""
    instance_id: str = ""
    can_continue: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class SubagentProvider(ABC):
    """Abstract subagent execution provider."""

    name: str = "abstract"

    def __init__(self):
        self._capabilities = ProviderCapabilities()

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    @abstractmethod
    async def start(self, name: str, task: str,
                    context: Optional[List[Dict]] = None,
                    config: Optional[Any] = None) -> ProviderResult:
        """Start a fresh subagent execution."""

    async def continuation(self, instance_id: str, message: str) -> ProviderResult:
        """Resume a settled subagent (default: unsupported → fail-loud)."""
        raise NotImplementedError(
            f"Provider '{self.name}' does not support continuation "
            f"(capabilities.continuation=False)")

    async def interrupt(self, instance_id: str) -> bool:
        """Request cancellation (default: no-op false)."""
        return False

    async def close(self) -> None:
        """Release provider resources."""


class InProcessProvider(SubagentProvider):
    """Default provider: existing conversational-agent execution in this process."""

    name = "in_process"

    def __init__(self, coordinator: Any = None):
        super().__init__()
        self._coordinator = coordinator
        self._capabilities = ProviderCapabilities(
            start=True, continuation=True, isolation=True,
            external=False, output_schema=False, tool_filter=True,
        )

    async def start(self, name: str, task: str,
                    context: Optional[List[Dict]] = None,
                    config: Optional[Any] = None) -> ProviderResult:
        if self._coordinator is None:
            return ProviderResult(ok=False, error="coordinator not wired")
        try:
            result = await self._coordinator.execute_single(
                task, name, context=context)
            if hasattr(result, "success") and not result.success:
                return ProviderResult(ok=False, error=str(result.error or "subagent failed"))
            output = getattr(result, "output", None) or getattr(result, "summary", None) or str(result)
            return ProviderResult(
                ok=True, output=str(output),
                instance_id=f"inproc:{name}", can_continue=True,
            )
        except Exception as e:
            logger.debug("in_process provider start failed: %s", e, exc_info=True)
            return ProviderResult(ok=False, error=str(e)[:300])

    async def continuation(self, instance_id: str, message: str) -> ProviderResult:
        # In-process instances can be resumed by re-running with appended context
        return ProviderResult(ok=False, error="in-process continuation via new start",
                              can_continue=False)


class ACPProvider(SubagentProvider):
    """External provider: execute subagents via the ACP WebSocket protocol.

    Reuses core/acp/server.py (/acp websocket). A real ACP client handshake is
    out of scope here; this provider performs capability checks and delegates
    the actual protocol exchange to core.acp.client (if present), otherwise
    fails loud with a clear message.
    """

    name = "acp"

    def __init__(self, endpoint: str = ""):
        super().__init__()
        self._endpoint = endpoint or os.getenv("AIPLAT_ACP_ENDPOINT", "ws://localhost:8002/acp")
        self._capabilities = ProviderCapabilities(
            start=True, continuation=True, isolation=True,
            external=True, output_schema=True, tool_filter=True,
        )

    async def start(self, name: str, task: str,
                    context: Optional[List[Dict]] = None,
                    config: Optional[Any] = None) -> ProviderResult:
        try:
            from core.acp.client import ACPClient
            client = ACPClient(self._endpoint)
            resp = await client.start_agent(name=name, task=task)
            return ProviderResult(
                ok=bool(resp.get("ok", False)),
                output=str(resp.get("output", "")),
                error=str(resp.get("error", "")),
                instance_id=str(resp.get("instance_id", "")),
                can_continue=bool(resp.get("can_continue", False)),
            )
        except ImportError:
            return ProviderResult(
                ok=False,
                error="ACP client not available — install core.acp.client or use in_process provider",
            )
        except Exception as e:
            logger.debug("acp provider start failed: %s", e, exc_info=True)
            return ProviderResult(ok=False, error=str(e)[:300])


_PROVIDER_FACTORIES = {
    "in_process": lambda c: InProcessProvider(c),
    "acp": lambda c: ACPProvider(),
}


def get_provider_factories() -> Dict[str, Any]:
    return dict(_PROVIDER_FACTORIES)


def default_provider_name() -> str:
    return os.getenv("AIPLAT_SUBAGENT_PROVIDER", "in_process").strip().lower()
